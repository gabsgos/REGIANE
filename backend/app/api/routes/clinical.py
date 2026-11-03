from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    require_csrf_permission,
    require_permission,
)
from backend.app.db.models import (
    Appointment,
    AuditLog,
    ClinicalDocument,
    Patient,
    Payment,
    Professional,
)
from backend.app.db.session import get_db_session

router = APIRouter(tags=["clinica"])


def cpf_digits(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\D", "", value)


def valid_cpf(value: str) -> bool:
    cpf = cpf_digits(value) or ""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(cpf[index]) * (size + 1 - index) for index in range(size))
        digit = (total * 10 % 11) % 10
        if digit != int(cpf[size]):
            return False
    return True


class PatientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    cpf: str | None = None
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    address_json: dict[str, Any] | None = None

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = cpf_digits(value)
        if not normalized or not valid_cpf(normalized):
            raise ValueError("CPF invalido")
        return normalized


class PatientUpdate(PatientCreate):
    expected_version: int = Field(ge=1)
    active: bool = True


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cpf: str | None
    birth_date: date | None
    phone: str | None
    email: str | None
    address_json: dict[str, Any] | None
    active: bool
    row_version: int


class AppointmentCreate(BaseModel):
    patient_id: int
    exam_date: date
    event_type_id: int | None = None
    doctor_id: int | None = None
    psychologist_id: int | None = None
    origin_id: int | None = None
    renach: str | None = Field(default=None, max_length=20)
    status: str = Field(default="aberto", pattern="^(aberto|concluido|cancelado)$")
    result: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class AppointmentUpdate(AppointmentCreate):
    expected_version: int = Field(ge=1)


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    legacy_code: str | None
    renach: str | None
    exam_date: date
    event_type_id: int | None
    doctor_id: int | None
    psychologist_id: int | None
    origin_id: int | None
    status: str
    result: str | None
    notes: str | None
    row_version: int
    workflow_status: str
    reanalysis_required: bool
    operational_observation: str | None
    scheduled_at: datetime | None
    operational_status: str
    service_type_id: int | None
    source_kind: str


class ProfessionalAbsence(BaseModel):
    reason: str = Field(min_length=5, max_length=255)
    expected_version: int = Field(ge=1)


class ReanalysisRequest(BaseModel):
    observation: str = Field(min_length=5, max_length=500)
    expected_version: int = Field(ge=1)


def audit(
    db: Session,
    context: AuthContext,
    action: str,
    entity_type: str,
    entity_id: int,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    db.add(
        AuditLog(
            occurred_at=datetime.now(UTC).replace(tzinfo=None),
            user_id=context.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            before_json=before,
            after_json=after,
            request_id=None,
        )
    )


def appointment_scope(statement, context: AuthContext):
    if "medico" in context.roles and "gerente" not in context.roles:
        if not context.user.professional_id:
            return statement.where(False)
        return statement.where(
            or_(
                Appointment.doctor_id == context.user.professional_id,
                Appointment.psychologist_id == context.user.professional_id,
            )
        )
    return statement


def sync_appointment_workflow(db: Session, appointment: Appointment) -> str:
    immutable_states = {"PDF_AUTENTICADO", "DISPONIVEL_RECEPCAO", "ENTREGUE", "EMENDADO"}
    if appointment.operational_status == "COMPLETED":
        appointment.workflow_status = "CONCLUIDO_PAGAMENTO_INDEPENDENTE"
    elif appointment.operational_status == "TEMPORARILY_UNFIT":
        appointment.workflow_status = "TEMPORARILY_UNFIT"
    elif appointment.status == "cancelado":
        if appointment.workflow_status != "CANCELADO_FALTA_PROFISSIONAL":
            appointment.workflow_status = "CANCELADO"
    elif appointment.workflow_status in immutable_states:
        pass
    elif appointment.reanalysis_required:
        appointment.workflow_status = "REANALISE_PENDENTE"
    else:
        paid = db.scalar(
            select(Payment.id).where(
                Payment.appointment_id == appointment.id, Payment.status == "pago"
            )
        )
        appointment.workflow_status = (
            "LIBERADO_PARA_MEDICO"
            if paid and (appointment.doctor_id or appointment.psychologist_id)
            else "PAGAMENTO_PENDENTE"
        )
    return appointment.workflow_status


def professional_can_act(db: Session, context: AuthContext, appointment: Appointment) -> bool:
    if not context.user.professional_id:
        return False
    professional = db.get(Professional, context.user.professional_id)
    if (
        not professional
        or not professional.active
        or professional.council_type not in {"CRM", "CRP"}
        or not professional.council_number.strip()
    ):
        return False
    if "gerente" not in context.roles and context.user.professional_id not in {
        appointment.doctor_id,
        appointment.psychologist_id,
    }:
        return False
    return appointment.status == "aberto"


@router.get("/patients")
def list_patients(
    context: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    statement = select(Patient).where(Patient.active.is_(True))
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(or_(Patient.name.ilike(term), Patient.cpf.like(term)))
    if "medico" in context.roles and "gerente" not in context.roles:
        appointment_ids = appointment_scope(select(Appointment.patient_id), context)
        statement = statement.where(Patient.id.in_(appointment_ids))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        db.scalars(statement.order_by(Patient.name).offset((page - 1) * page_size).limit(page_size))
    )
    return {"items": [PatientOut.model_validate(item) for item in items], "total": total}


@router.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    context: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Patient:
    statement = select(Patient).where(Patient.id == patient_id)
    if "medico" in context.roles and "gerente" not in context.roles:
        statement = statement.where(
            Patient.id.in_(appointment_scope(select(Appointment.patient_id), context))
        )
    patient = db.scalar(statement)
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    return patient


@router.post("/patients", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("demographic.create", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Patient:
    patient = Patient(**payload.model_dump(), active=True)
    db.add(patient)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="CPF ja cadastrado") from exc
    audit(
        db,
        context,
        "create",
        "patients",
        patient.id,
        None,
        PatientOut.model_validate(patient).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.put("/patients/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("demographic.write", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Patient:
    current = db.get(Patient, patient_id)
    if not current:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    before = PatientOut.model_validate(current).model_dump(mode="json")
    values = payload.model_dump(exclude={"expected_version"})
    result = db.execute(
        update(Patient)
        .where(Patient.id == patient_id, Patient.row_version == payload.expected_version)
        .values(
            **values,
            row_version=Patient.row_version + 1,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    db.expire_all()
    updated = db.get(Patient, patient_id)
    audit(
        db,
        context,
        "update",
        "patients",
        patient_id,
        before,
        PatientOut.model_validate(updated).model_dump(mode="json"),
    )
    db.commit()
    return updated


@router.get("/appointments")
def list_appointments(
    context: Annotated[
        AuthContext,
        Depends(require_permission("schedule.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
    search: str | None = Query(default=None, max_length=120),
    date_from: date | None = None,
    date_to: date | None = None,
    appointment_status: str | None = Query(default=None, alias="status"),
    patient_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    statement = appointment_scope(select(Appointment), context)
    if date_from:
        statement = statement.where(Appointment.exam_date >= date_from)
    if date_to:
        statement = statement.where(Appointment.exam_date <= date_to)
    if appointment_status:
        statement = statement.where(Appointment.status == appointment_status)
    if patient_id:
        statement = statement.where(Appointment.patient_id == patient_id)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.join(Patient).where(
            or_(Patient.name.ilike(term), Patient.cpf.like(term), Appointment.renach.like(term))
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        db.scalars(
            statement.order_by(Appointment.exam_date.desc(), Appointment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {"items": [AppointmentOut.model_validate(item) for item in items], "total": total}


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    context: Annotated[
        AuthContext,
        Depends(require_permission("schedule.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Appointment:
    item = db.scalar(
        appointment_scope(select(Appointment).where(Appointment.id == appointment_id), context)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    return item


@router.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("schedule.write", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Appointment:
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(status_code=422, detail="Paciente inexistente")
    item = Appointment(
        **payload.model_dump(),
        created_by_id=context.user.id,
        workflow_status="PAGAMENTO_PENDENTE",
    )
    db.add(item)
    db.flush()
    audit(
        db,
        context,
        "create",
        "appointments",
        item.id,
        None,
        AppointmentOut.model_validate(item).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(item)
    return item


@router.put("/appointments/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("schedule.write", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> Appointment:
    current = db.get(Appointment, appointment_id)
    if not current:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    before = AppointmentOut.model_validate(current).model_dump(mode="json")
    values = payload.model_dump(exclude={"expected_version"})
    result = db.execute(
        update(Appointment)
        .where(
            Appointment.id == appointment_id, Appointment.row_version == payload.expected_version
        )
        .values(
            **values,
            row_version=Appointment.row_version + 1,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    db.expire_all()
    updated = db.get(Appointment, appointment_id)
    sync_appointment_workflow(db, updated)
    audit(
        db,
        context,
        "update",
        "appointments",
        appointment_id,
        before,
        AppointmentOut.model_validate(updated).model_dump(mode="json"),
    )
    db.commit()
    return updated


@router.post("/appointments/{appointment_id}/professional-absence")
def cancel_for_professional_absence(
    appointment_id: int,
    payload: ProfessionalAbsence,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("schedule.cancel", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    if appointment.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    if appointment.workflow_status in {"PDF_AUTENTICADO", "ENTREGUE", "EMENDADO"}:
        raise HTTPException(status_code=409, detail="Atendimento clinico ja concluido")
    before = AppointmentOut.model_validate(appointment).model_dump(mode="json")
    appointment.status = "cancelado"
    appointment.workflow_status = "CANCELADO_FALTA_PROFISSIONAL"
    appointment.operational_observation = payload.reason.strip()
    appointment.row_version += 1
    db.flush()
    after = AppointmentOut.model_validate(appointment).model_dump(mode="json")
    audit(db, context, "professional_absence", "appointments", appointment.id, before, after)
    db.commit()
    return after


@router.get("/clinical/worklist")
def clinical_worklist(
    context: Annotated[
        AuthContext,
        Depends(require_permission("clinical_queue.read", "gerente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    if not context.user.professional_id:
        return {"items": [], "total": 0}
    professional = db.get(Professional, context.user.professional_id)
    if (
        not professional
        or not professional.active
        or professional.council_type not in {"CRM", "CRP"}
    ):
        return {"items": [], "total": 0}
    statement = (
        select(Appointment, Patient)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            Appointment.status == "aberto",
            or_(
                Appointment.doctor_id == context.user.professional_id,
                Appointment.psychologist_id == context.user.professional_id,
            ),
            Appointment.id.in_(select(Payment.appointment_id).where(Payment.status == "pago")),
        )
        .order_by(Appointment.exam_date, Appointment.id)
    )
    rows = db.execute(statement).all()
    items = [
        {
            "appointment_id": appointment.id,
            "patient_id": patient.id,
            "patient_name": patient.name,
            "exam_date": appointment.exam_date.isoformat(),
            "event_type_id": appointment.event_type_id,
            "renach": appointment.renach,
            "workflow_status": appointment.workflow_status,
            "reanalysis_required": appointment.reanalysis_required,
            "operational_observation": appointment.operational_observation,
            "row_version": appointment.row_version,
        }
        for appointment, patient in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/clinical/appointments/{appointment_id}/reanalysis")
def mark_reanalysis(
    appointment_id: int,
    payload: ReanalysisRequest,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("document.authenticate", "gerente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or not professional_can_act(db, context, appointment):
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    if appointment.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    if db.scalar(
        select(func.count())
        .select_from(ClinicalDocument)
        .where(
            ClinicalDocument.appointment_id == appointment.id,
            ClinicalDocument.active.is_(True),
        )
    ):
        raise HTTPException(status_code=409, detail="Atendimento ja possui PDF ativo")
    appointment.reanalysis_required = True
    appointment.operational_observation = payload.observation.strip()
    appointment.workflow_status = "REANALISE_PENDENTE"
    appointment.row_version += 1
    audit(
        db,
        context,
        "reanalysis",
        "appointments",
        appointment.id,
        None,
        {
            "reanalysis_required": True,
            "operational_observation": appointment.operational_observation,
        },
    )
    db.commit()
    return {
        "appointment_id": appointment.id,
        "workflow_status": appointment.workflow_status,
        "reanalysis_required": True,
        "operational_observation": appointment.operational_observation,
        "row_version": appointment.row_version,
    }
