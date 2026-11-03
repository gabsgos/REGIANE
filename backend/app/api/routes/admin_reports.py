from __future__ import annotations

import csv
import io
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import delete, distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    require_csrf_permission,
    require_permission,
)
from backend.app.api.routes.clinical import audit
from backend.app.core.security import hash_password
from backend.app.db.models import (
    Appointment,
    AuthSession,
    EventType,
    MigrationIssue,
    Patient,
    Payment,
    PaymentItem,
    Professional,
    Permission,
    Receipt,
    Role,
    User,
    UserRole,
)
from backend.app.db.session import get_db_session

router = APIRouter(tags=["administracao", "relatorios"])
RoleName = Literal["gerente", "atendente", "medico"]


def validate_cpf(value: str) -> str:
    if len(set(value)) == 1:
        raise ValueError("CPF invalido")
    numbers = [int(digit) for digit in value]
    for length in (9, 10):
        pairs = zip(numbers[:length], range(length + 1, 1, -1), strict=True)
        total = sum(number * weight for number, weight in pairs)
        digit = 11 - total % 11
        if (0 if digit >= 10 else digit) != numbers[length]:
            raise ValueError("CPF invalido")
    return value


CPF = Annotated[str, Field(pattern=r"^\d{11}$"), AfterValidator(validate_cpf)]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    cpf: CPF
    birth_date: date
    phone: str = Field(min_length=8, max_length=20)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    address: str = Field(min_length=5, max_length=500)
    role: RoleName
    professional_id: int | None = None


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    cpf: CPF
    birth_date: date
    phone: str = Field(min_length=8, max_length=20)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    address: str = Field(min_length=5, max_length=500)
    role: RoleName
    professional_id: int | None = None
    active: bool
    expected_version: int = Field(ge=1)


def user_json(db: Session, user: User) -> dict:
    roles = list(
        db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "cpf": user.cpf,
        "birth_date": user.birth_date,
        "phone": user.phone,
        "email": user.email,
        "address": user.address,
        "roles": roles,
        "professional_id": user.professional_id,
        "active": user.active,
        "must_reset_password": user.must_reset_password,
        "access_version": user.access_version,
        "row_version": user.row_version,
    }


def audit_user_json(data: dict) -> dict:
    safe = dict(data)
    cpf = safe.get("cpf")
    safe["cpf"] = f"***{cpf[-3:]}" if cpf else None
    phone = safe.get("phone")
    safe["phone"] = f"***{phone[-4:]}" if phone else None
    email = safe.get("email")
    if email and "@" in email:
        local, domain = email.split("@", 1)
        safe["email"] = f"{local[:1]}***@{domain}"
    safe.pop("birth_date", None)
    safe.pop("address", None)
    return safe


def role_by_name(db: Session, role_name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise HTTPException(status_code=422, detail="Perfil inexistente")
    return role


def validate_professional_link(
    db: Session, role_name: RoleName, professional_id: int | None
) -> None:
    if role_name == "medico" and not professional_id:
        raise HTTPException(status_code=422, detail="Profissional obrigatorio para perfil medico")
    if not professional_id:
        return
    professional = db.get(Professional, professional_id)
    if (
        not professional
        or not professional.active
        or professional.council_type not in {"CRM", "CRP"}
        or not professional.council_number.strip()
    ):
        raise HTTPException(status_code=422, detail="CRM ou CRP ativo obrigatorio")


@router.get("/admin/users")
def list_users(
    context: Annotated[AuthContext, Depends(require_permission("user.read", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    statement = select(User).where(User.workspace_id == context.user.workspace_id)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    users = list(db.scalars(statement.order_by(User.display_name).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [user_json(db, user) for user in users], "page": page, "page_size": page_size, "total": total}


@router.get("/admin/permissions")
def list_permissions(
    _: Annotated[AuthContext, Depends(require_permission("user.read", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    permissions = list(db.scalars(select(Permission).where(Permission.active.is_(True)).order_by(Permission.key)))
    return {"items": [{"id": item.id, "key": item.key, "resource": item.resource, "action": item.action, "sensitivity": item.sensitivity, "delegable": item.delegable, "active": item.active} for item in permissions]}


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("user.create", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    role = role_by_name(db, payload.role)
    validate_professional_link(db, payload.role, payload.professional_id)
    temporary_password = secrets.token_urlsafe(18)
    user = User(
        username=payload.username.lower(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(temporary_password),
        cpf=payload.cpf,
        birth_date=payload.birth_date,
        phone=payload.phone.strip(),
        email=payload.email.strip().lower(),
        address=payload.address.strip(),
        professional_id=payload.professional_id,
        workspace_id=context.user.workspace_id,
        manager_id=None if payload.role == "gerente" else context.user.id,
        active=True,
        must_reset_password=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuario ja existe") from exc
    db.add(UserRole(user_id=user.id, role_id=role.id))
    result = user_json(db, user)
    audit(db, context, "create", "users", user.id, None, audit_user_json(result))
    db.commit()
    return {"user": result, "temporary_password": temporary_password}


@router.put("/admin/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("user.manage", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if user.workspace_id != context.user.workspace_id:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if user.id == context.user.id and not payload.active:
        raise HTTPException(status_code=409, detail="Nao e permitido desativar a propria conta")
    if user.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    before = user_json(db, user)
    role = role_by_name(db, payload.role)
    validate_professional_link(db, payload.role, payload.professional_id)
    current_role = db.scalar(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    access_changed = (
        current_role != payload.role
        or user.professional_id != payload.professional_id
        or user.active != payload.active
    )
    if user.id == context.user.id and access_changed:
        raise HTTPException(status_code=409, detail="Nao e permitido alterar o proprio acesso")
    if current_role == "gerente" and (payload.role != "gerente" or not payload.active):
        active_managers = db.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(Role.name == "gerente", User.active.is_(True), User.id != user.id)
        )
        if not active_managers:
            raise HTTPException(status_code=409, detail="Ultimo gestor ativo protegido")
    user.display_name = payload.display_name.strip()
    user.cpf = payload.cpf
    user.birth_date = payload.birth_date
    user.phone = payload.phone.strip()
    user.email = payload.email.strip().lower()
    user.address = payload.address.strip()
    user.professional_id = payload.professional_id
    user.active = payload.active
    if access_changed:
        user.access_version += 1
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuario ou CPF ja existe") from exc
    result = user_json(db, user)
    audit(
        db,
        context,
        "update",
        "users",
        user.id,
        audit_user_json(before),
        audit_user_json(result),
    )
    db.commit()
    return result


@router.post("/admin/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("user.reset_password", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    temporary_password = secrets.token_urlsafe(18)
    user.password_hash = hash_password(temporary_password)
    user.must_reset_password = True
    user.access_version += 1
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, context, "reset_password", "users", user.id, None, {"reset_required": True})
    db.commit()
    return {"temporary_password": temporary_password, "must_reset_password": True}


def report_appointment_ids(
    date_from: date,
    date_to: date,
    professional_id: int | None,
    event_type_id: int | None,
):
    statement = select(Appointment.id).where(
        Appointment.exam_date >= date_from,
        Appointment.exam_date <= date_to,
    )
    if professional_id:
        statement = statement.where(
            or_(
                Appointment.doctor_id == professional_id,
                Appointment.psychologist_id == professional_id,
            )
        )
    if event_type_id:
        statement = statement.where(Appointment.event_type_id == event_type_id)
    return statement


@router.get("/reports/appointments")
def appointment_report(
    _: Annotated[
        AuthContext, Depends(require_permission("report.operational", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
    date_from: date,
    date_to: date,
    professional_id: int | None = None,
    event_type_id: int | None = None,
    payment_method: str | None = Query(default=None, pattern="^(pix|dinheiro|cartao|cheque)$"),
) -> dict:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="Periodo invalido")
    ids = report_appointment_ids(date_from, date_to, professional_id, event_type_id)
    if payment_method:
        ids = ids.where(
            Appointment.id.in_(
                select(Payment.appointment_id)
                .join(PaymentItem, PaymentItem.payment_id == Payment.id)
                .where(PaymentItem.method == payment_method)
            )
        )
    appointment_count = db.scalar(select(func.count()).select_from(ids.subquery())) or 0
    patient_count = (
        db.scalar(
            select(func.count(distinct(Appointment.patient_id))).where(Appointment.id.in_(ids))
        )
        or 0
    )
    paid_total = db.scalar(
        select(func.sum(Payment.total_amount)).where(
            Payment.appointment_id.in_(ids), Payment.status == "pago"
        )
    ) or Decimal("0.00")
    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "professional_id": professional_id,
            "event_type_id": event_type_id,
            "payment_method": payment_method,
        },
        "appointment_count": appointment_count,
        "patient_count": patient_count,
        "paid_total": str(paid_total),
    }


def safe_csv(value: object) -> str:
    text = str(value if value is not None else "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


@router.get("/reports/appointments.csv")
def export_appointments(
    context: Annotated[
        AuthContext, Depends(require_permission("report.operational", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
    date_from: date,
    date_to: date,
) -> StreamingResponse:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="Periodo invalido")
    rows = db.execute(
        select(
            Appointment.id,
            Appointment.exam_date,
            Patient.id.label("patient_id"),
            Patient.name,
            Appointment.status,
            EventType.name.label("event_type"),
        )
        .join(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(EventType, EventType.id == Appointment.event_type_id)
        .where(Appointment.exam_date >= date_from, Appointment.exam_date <= date_to)
        .order_by(Appointment.exam_date, Appointment.id)
    ).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["atendimento", "data", "paciente_id", "paciente", "status", "evento"])
    for row in rows:
        writer.writerow([safe_csv(value) for value in row])
    audit(
        db,
        context,
        "export",
        "reports",
        0,
        None,
        {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "rows": len(rows)},
    )
    db.commit()
    content = "\ufeff" + output.getvalue()
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=atendimentos.csv"},
    )


@router.get("/reports/daily-closing")
def daily_closing(
    _: Annotated[AuthContext, Depends(require_permission("finance.reconcile", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
    closing_date: date,
) -> dict:
    start = datetime.combine(closing_date, time.min)
    end = start + timedelta(days=1)
    paid_total = db.scalar(
        select(func.sum(Payment.total_amount)).where(
            Payment.status == "pago", Payment.paid_at >= start, Payment.paid_at < end
        )
    ) or Decimal("0.00")
    receipt_total = db.scalar(
        select(func.sum(Receipt.amount)).where(Receipt.issued_at == closing_date)
    ) or Decimal("0.00")
    return {
        "closing_date": closing_date.isoformat(),
        "paid_total": str(paid_total),
        "receipt_total": str(receipt_total),
        "difference": str(paid_total - receipt_total),
    }


@router.get("/reports/migration-issues")
def migration_issues(
    _: Annotated[
        AuthContext, Depends(require_permission("migration_issue.read", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    grouped = db.execute(
        select(MigrationIssue.issue_code, MigrationIssue.status, func.count())
        .group_by(MigrationIssue.issue_code, MigrationIssue.status)
        .order_by(MigrationIssue.issue_code)
    ).all()
    return {
        "total": sum(count for _, _, count in grouped),
        "groups": [
            {"issue_code": code, "status": issue_status, "count": count}
            for code, issue_status, count in grouped
        ],
    }
