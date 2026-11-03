from __future__ import annotations

import csv
import io
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    require_csrf_permission,
    require_permission,
)
from backend.app.api.routes.admin_reports import safe_csv
from backend.app.api.routes.clinical import audit, sync_appointment_workflow
from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    Patient,
    Payment,
    PaymentItem,
    Professional,
    Receipt,
    User,
)
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/finance", tags=["financeiro"])
PaymentMethod = Literal["pix", "dinheiro"]
BUSINESS_TIMEZONE = ZoneInfo(get_settings().business_timezone)


def business_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(BUSINESS_TIMEZONE).date()


def utc_day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start = datetime.combine(date_from, time.min, BUSINESS_TIMEZONE)
    end = datetime.combine(date_to + timedelta(days=1), time.min, BUSINESS_TIMEZONE)
    return (
        start.astimezone(UTC).replace(tzinfo=None),
        end.astimezone(UTC).replace(tzinfo=None),
    )


def validate_report_period(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="Periodo invalido")


def payment_period_filters(date_from: date, date_to: date, user_id: int | None = None) -> tuple:
    start, end = utc_day_bounds(date_from, date_to)
    filters = [Payment.paid_at >= start, Payment.paid_at < end]
    if user_id is not None:
        filters.append(Payment.created_by_id == user_id)
    return tuple(filters)


def report_payment_rows(db: Session, filters: tuple, offset: int = 0, limit: int | None = None):
    statement = (
        select(Payment, Patient.name, User.display_name)
        .join(Appointment, Appointment.id == Payment.appointment_id)
        .join(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(User, User.id == Payment.created_by_id)
        .where(*filters)
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
        .offset(offset)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return db.execute(statement).all()


def payment_methods(db: Session, payment_ids: list[int]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {payment_id: [] for payment_id in payment_ids}
    if not payment_ids:
        return result
    for payment_id, method in db.execute(
        select(PaymentItem.payment_id, PaymentItem.method)
        .where(PaymentItem.payment_id.in_(payment_ids))
        .order_by(PaymentItem.id)
    ):
        result[payment_id].append(method)
    return result


def serialize_report_rows(db: Session, rows) -> list[dict]:
    methods = payment_methods(db, [payment.id for payment, _, _ in rows])
    return [
        {
            "id": payment.id,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "appointment_id": payment.appointment_id,
            "patient": patient_name,
            "user": user_name or "Legado/nao identificado",
            "methods": methods[payment.id],
            "status": payment.status,
            "total_amount": str(payment.total_amount),
        }
        for payment, patient_name, user_name in rows
    ]


class PaymentItemIn(BaseModel):
    method: PaymentMethod
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(default=None, max_length=100)


class PaymentCreate(BaseModel):
    appointment_id: int
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    items: list[PaymentItemIn] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def items_equal_total(self):
        if sum((item.amount for item in self.items), Decimal("0.00")) != self.total_amount:
            raise ValueError("Soma dos itens difere do total")
        return self


class ReversalRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=255)
    expected_version: int = Field(ge=1)


class ReceiptCreate(BaseModel):
    appointment_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    recipient_name: str | None = Field(default=None, max_length=150)


def payment_json(db: Session, payment: Payment) -> dict:
    items = list(
        db.scalars(
            select(PaymentItem).where(PaymentItem.payment_id == payment.id).order_by(PaymentItem.id)
        )
    )
    return {
        "id": payment.id,
        "appointment_id": payment.appointment_id,
        "total_amount": str(payment.total_amount),
        "status": payment.status,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "reversed_at": payment.reversed_at.isoformat() if payment.reversed_at else None,
        "reversal_reason": payment.reversal_reason,
        "row_version": payment.row_version,
        "commission_rate": str(payment.commission_rate)
        if payment.commission_rate is not None
        else None,
        "professional_amount": str(payment.professional_amount)
        if payment.professional_amount is not None
        else None,
        "clinic_amount": str(payment.clinic_amount) if payment.clinic_amount is not None else None,
        "items": [
            {
                "id": item.id,
                "method": item.method,
                "amount": str(item.amount),
                "reference": item.reference,
            }
            for item in items
        ],
    }


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("finance.receive", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, payload.appointment_id)
    if not appointment:
        raise HTTPException(status_code=422, detail="Atendimento inexistente")
    if db.scalar(
        select(Payment.id).where(Payment.appointment_id == appointment.id, Payment.status == "pago")
    ):
        raise HTTPException(status_code=409, detail="Atendimento ja possui pagamento ativo")
    professional_id = appointment.doctor_id or appointment.psychologist_id
    professional = db.get(Professional, professional_id) if professional_id else None
    rate = professional.commission_rate if professional else Decimal("0.6000")
    professional_amount = (payload.total_amount * rate).quantize(Decimal("0.01"))
    now = datetime.now(UTC).replace(tzinfo=None)
    payment = Payment(
        appointment_id=payload.appointment_id,
        total_amount=payload.total_amount,
        status="pago",
        paid_at=now,
        created_by_id=context.user.id,
        commission_rate=rate,
        professional_amount=professional_amount,
        clinic_amount=payload.total_amount - professional_amount,
    )
    db.add(payment)
    db.flush()
    for item in payload.items:
        db.add(
            PaymentItem(
                payment_id=payment.id,
                method=item.method,
                amount=item.amount,
                reference=item.reference,
            )
        )
    sync_appointment_workflow(db, appointment)
    db.flush()
    after = payment_json(db, payment)
    audit(db, context, "create", "payments", payment.id, None, after)
    db.commit()
    return after


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: int,
    _: Annotated[AuthContext, Depends(require_permission("finance.read", "gerente", "atendente"))],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento nao encontrado")
    return payment_json(db, payment)


@router.post("/payments/{payment_id}/reverse")
def reverse_payment(
    payment_id: int,
    payload: ReversalRequest,
    context: Annotated[AuthContext, Depends(require_csrf_permission("finance.reverse", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento nao encontrado")
    if payment.status == "estornado":
        raise HTTPException(status_code=409, detail="Pagamento ja estornado")
    if payment.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    before = payment_json(db, payment)
    payment.status = "estornado"
    payment.reversed_at = datetime.now(UTC).replace(tzinfo=None)
    payment.reversal_reason = payload.reason
    payment.reversed_by_id = context.user.id
    appointment = db.get(Appointment, payment.appointment_id)
    if (
        appointment
        and appointment.operational_status != "COMPLETED"
        and appointment.workflow_status
        not in {
            "PDF_AUTENTICADO",
            "DISPONIVEL_RECEPCAO",
            "ENTREGUE",
            "EMENDADO",
        }
    ):
        appointment.workflow_status = "BLOQUEADO"
    db.flush()
    after = payment_json(db, payment)
    audit(db, context, "reverse", "payments", payment.id, before, after)
    db.commit()
    return after


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
def create_receipt(
    payload: ReceiptCreate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("finance.receive", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, payload.appointment_id)
    if not appointment:
        raise HTTPException(status_code=422, detail="Atendimento inexistente")
    patient = db.get(Patient, appointment.patient_id)
    today = business_today()
    receipt = Receipt(
        receipt_number=f"R-{today:%Y%m%d}-{secrets.token_hex(4).upper()}",
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        issued_at=today,
        amount=payload.amount,
        recipient_name=payload.recipient_name or (patient.name if patient else None),
    )
    db.add(receipt)
    db.flush()
    result = {
        "id": receipt.id,
        "receipt_number": receipt.receipt_number,
        "appointment_id": receipt.appointment_id,
        "issued_at": receipt.issued_at.isoformat(),
        "amount": str(receipt.amount),
        "recipient_name": receipt.recipient_name,
    }
    audit(db, context, "create", "receipts", receipt.id, None, result)
    db.commit()
    return result


@router.get("/summary")
def financial_summary(
    context: Annotated[AuthContext, Depends(require_permission("finance.read", "gerente", "atendente", "medico", "psicologo"))],
    db: Annotated[Session, Depends(get_db_session)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> dict:
    today = business_today()
    date_from = date_from or today
    date_to = date_to or today
    if "atendente" in context.roles:
        date_from = date_to = today
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="Periodo invalido")
    start, end = utc_day_bounds(date_from, date_to)
    base_filters = [
        Payment.status == "pago",
        Payment.paid_at >= start,
        Payment.paid_at < end,
    ]
    if "medico" in context.roles or "psicologo" in context.roles:
        if not context.user.professional_id:
            return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "paid_count": 0, "paid_total": "0.00", "by_method": {}, "reversal_count": 0}
        professional_filter = (
            Appointment.doctor_id == context.user.professional_id
            if "medico" in context.roles
            else Appointment.psychologist_id == context.user.professional_id
        )
        base_filters.extend([Payment.appointment_id == Appointment.id, professional_filter])
    total = db.scalar(select(func.sum(Payment.total_amount)).select_from(Payment).where(*base_filters)) or Decimal(
        "0.00"
    )
    count = db.scalar(select(func.count()).select_from(Payment).where(*base_filters)) or 0
    by_method_rows = db.execute(
        select(PaymentItem.method, func.sum(PaymentItem.amount))
        .join(Payment, Payment.id == PaymentItem.payment_id)
        .where(*base_filters)
        .group_by(PaymentItem.method)
    ).all()
    reversals = (
        db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.status == "estornado",
                Payment.reversed_at >= start,
                Payment.reversed_at < end,
            )
        )
        or 0
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "paid_count": count,
        "paid_total": str(total),
        "by_method": {method: str(amount) for method, amount in by_method_rows},
        "reversal_count": reversals,
    }


@router.get("/report")
def financial_report(
    _: Annotated[AuthContext, Depends(require_permission("finance.report", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
    date_from: date,
    date_to: date,
    user_id: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
) -> dict:
    validate_report_period(date_from, date_to)
    filters = payment_period_filters(date_from, date_to, user_id)
    paid_filters = (*filters, Payment.status == "pago")
    start, end = utc_day_bounds(date_from, date_to)

    paid_total = db.scalar(select(func.sum(Payment.total_amount)).where(*paid_filters)) or Decimal(
        "0.00"
    )
    paid_count = db.scalar(select(func.count()).select_from(Payment).where(*paid_filters)) or 0
    reversal_filters = [
        Payment.status == "estornado",
        Payment.reversed_at >= start,
        Payment.reversed_at < end,
    ]
    if user_id is not None:
        reversal_filters.append(Payment.created_by_id == user_id)
    reversal_count = (
        db.scalar(select(func.count()).select_from(Payment).where(*reversal_filters)) or 0
    )
    by_method = {
        method: str(amount)
        for method, amount in db.execute(
            select(PaymentItem.method, func.sum(PaymentItem.amount))
            .join(Payment, Payment.id == PaymentItem.payment_id)
            .where(*paid_filters)
            .group_by(PaymentItem.method)
            .order_by(PaymentItem.method)
        )
    }

    series: dict[str, dict[str, Decimal | int]] = {}
    for paid_at, amount in db.execute(
        select(Payment.paid_at, Payment.total_amount).where(*paid_filters).order_by(Payment.paid_at)
    ):
        bucket = paid_at.replace(tzinfo=UTC).astimezone(BUSINESS_TIMEZONE).date().isoformat()
        point = series.setdefault(bucket, {"total": Decimal("0.00"), "count": 0})
        point["total"] += amount
        point["count"] += 1

    receipt_filters = [Receipt.issued_at >= date_from, Receipt.issued_at <= date_to]
    if user_id is not None:
        receipt_filters.append(
            Receipt.appointment_id.in_(
                select(Payment.appointment_id).where(Payment.created_by_id == user_id)
            )
        )
    receipt_total = db.scalar(select(func.sum(Receipt.amount)).where(*receipt_filters)) or Decimal(
        "0.00"
    )
    movement_count = db.scalar(select(func.count()).select_from(Payment).where(*filters)) or 0
    rows = report_payment_rows(db, filters, offset=(page - 1) * page_size, limit=page_size)

    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "user_id": user_id,
        },
        "summary": {
            "paid_total": str(paid_total),
            "paid_count": paid_count,
            "average_ticket": str(paid_total / paid_count if paid_count else Decimal("0.00")),
            "reversal_count": reversal_count,
        },
        "by_method": by_method,
        "series": [
            {"date": bucket, "total": str(point["total"]), "count": point["count"]}
            for bucket, point in series.items()
        ],
        "comparison": {
            "payment_total": str(paid_total),
            "receipt_total": str(receipt_total),
            "difference": str(paid_total - receipt_total),
        },
        "movements": {
            "items": serialize_report_rows(db, rows),
            "page": page,
            "page_size": page_size,
            "total": movement_count,
            "pages": max(1, (movement_count + page_size - 1) // page_size),
        },
    }


@router.get("/report.csv")
def export_financial_report(
    context: Annotated[AuthContext, Depends(require_permission("finance.export", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
    date_from: date,
    date_to: date,
    user_id: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    validate_report_period(date_from, date_to)
    filters = payment_period_filters(date_from, date_to, user_id)
    items = serialize_report_rows(db, report_payment_rows(db, filters))
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        ["pagamento", "data", "atendimento", "paciente", "usuario", "formas", "status", "valor"]
    )
    for item in items:
        writer.writerow(
            [
                safe_csv(item["id"]),
                safe_csv(item["paid_at"]),
                safe_csv(item["appointment_id"]),
                safe_csv(item["patient"]),
                safe_csv(item["user"]),
                safe_csv(", ".join(item["methods"])),
                safe_csv(item["status"]),
                safe_csv(item["total_amount"]),
            ]
        )
    audit(
        db,
        context,
        "export",
        "financial_report",
        0,
        None,
        {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "user_id": user_id,
            "rows": len(items),
        },
    )
    db.commit()
    return StreamingResponse(
        iter([("\ufeff" + output.getvalue()).encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="relatorio-financeiro.csv"'},
    )


@router.get("/patients/{patient_id}/report")
def patient_financial_report(
    patient_id: int,
    _: Annotated[AuthContext, Depends(require_permission("finance.read", "gerente", "atendente"))],
    db: Annotated[Session, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
) -> dict:
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    appointment_ids = select(Appointment.id).where(Appointment.patient_id == patient_id)
    payment_scope = Payment.appointment_id.in_(appointment_ids)
    totals = {
        status_name: db.scalar(
            select(func.sum(Payment.total_amount)).where(
                payment_scope, Payment.status == status_name
            )
        )
        or Decimal("0.00")
        for status_name in ("pago", "pendente", "estornado")
    }
    charged_total = sum(totals.values(), Decimal("0.00"))

    payments = list(
        db.scalars(
            select(Payment)
            .where(payment_scope)
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    payment_count = db.scalar(select(func.count()).select_from(Payment).where(payment_scope)) or 0
    methods = payment_methods(db, [payment.id for payment in payments])
    appointments = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.exam_date.desc(), Appointment.id.desc())
            .limit(100)
        )
    )
    receipts = list(
        db.scalars(
            select(Receipt)
            .where(Receipt.patient_id == patient_id)
            .order_by(Receipt.issued_at.desc(), Receipt.id.desc())
            .limit(100)
        )
    )

    monthly: dict[str, dict[str, Decimal | int]] = {}
    running_total = Decimal("0.00")
    paid_rows = db.execute(
        select(Payment.paid_at, Payment.total_amount)
        .where(payment_scope, Payment.status == "pago")
        .order_by(Payment.paid_at)
    ).all()
    appointment_rows = db.execute(
        select(Appointment.exam_date, func.count())
        .where(Appointment.patient_id == patient_id)
        .group_by(Appointment.exam_date)
        .order_by(Appointment.exam_date)
    ).all()
    for paid_at, amount in paid_rows:
        month = paid_at.replace(tzinfo=UTC).astimezone(BUSINESS_TIMEZONE).strftime("%Y-%m")
        point = monthly.setdefault(
            month, {"payments": Decimal("0.00"), "appointments": 0, "balance": Decimal("0.00")}
        )
        point["payments"] += amount
    for exam_date, count in appointment_rows:
        month = exam_date.strftime("%Y-%m")
        monthly.setdefault(
            month, {"payments": Decimal("0.00"), "appointments": 0, "balance": Decimal("0.00")}
        )["appointments"] += count
    for month in sorted(monthly):
        point = monthly[month]
        running_total += point["payments"]
        point["balance"] = running_total

    return {
        "patient": {"id": patient.id, "name": patient.name, "cpf": patient.cpf},
        "summary": {
            "charged_total": str(charged_total),
            "received_total": str(totals["pago"]),
            "pending_total": str(totals["pendente"]),
            "reversed_total": str(totals["estornado"]),
        },
        "monthly": [
            {
                "month": month,
                "payments": str(point["payments"]),
                "appointments": point["appointments"],
                "balance": str(point["balance"]),
            }
            for month, point in sorted(monthly.items())
        ],
        "payments": {
            "items": [
                {
                    "id": payment.id,
                    "appointment_id": payment.appointment_id,
                    "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
                    "methods": methods[payment.id],
                    "status": payment.status,
                    "amount": str(payment.total_amount),
                    "reversal_reason": payment.reversal_reason,
                }
                for payment in payments
            ],
            "page": page,
            "pages": max(1, (payment_count + page_size - 1) // page_size),
            "total": payment_count,
        },
        "appointments": [
            {"id": item.id, "date": item.exam_date.isoformat(), "status": item.status}
            for item in appointments
        ],
        "receipts": [
            {
                "number": item.receipt_number,
                "date": item.issued_at.isoformat(),
                "amount": str(item.amount),
            }
            for item in receipts
        ],
    }


@router.get("/patients/{patient_id}/report.csv")
def export_patient_financial_report(
    patient_id: int,
    context: Annotated[
        AuthContext,
        Depends(require_permission("finance.export", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> StreamingResponse:
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    filters = (
        Payment.appointment_id.in_(
            select(Appointment.id).where(Appointment.patient_id == patient_id)
        ),
    )
    items = serialize_report_rows(db, report_payment_rows(db, filters))
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["pagamento", "data", "atendimento", "formas", "status", "valor"])
    for item in items:
        writer.writerow(
            [
                safe_csv(item["id"]),
                safe_csv(item["paid_at"]),
                safe_csv(item["appointment_id"]),
                safe_csv(", ".join(item["methods"])),
                safe_csv(item["status"]),
                safe_csv(item["total_amount"]),
            ]
        )
    audit(
        db,
        context,
        "export",
        "patient_financial_report",
        patient_id,
        None,
        {"rows": len(items)},
    )
    db.commit()
    return StreamingResponse(
        iter([("\ufeff" + output.getvalue()).encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="financeiro-paciente-{patient_id}.csv"'
        },
    )
