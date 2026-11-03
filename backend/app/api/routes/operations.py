from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext, require_csrf_permission, require_permission
from backend.app.api.routes.clinical import audit, cpf_digits, valid_cpf
from backend.app.db.models import (
    AgendaImportBatch,
    AgendaImportRow,
    Appointment,
    ClinicalDocument,
    Patient,
    Professional,
    ServiceType,
)
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/operations", tags=["operacao-detran"])


class StrictPatientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    birth_date: date
    cpf: str
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    address_json: dict | None = None
    gender: str | None = Field(default=None, max_length=20)
    marital_status: str | None = Field(default=None, max_length=30)
    process_type: str | None = Field(default=None, max_length=80)
    observations: str | None = None

    @field_validator("cpf")
    @classmethod
    def normalize_cpf(cls, value: str) -> str:
        normalized = cpf_digits(value) or ""
        if not valid_cpf(normalized):
            raise ValueError("CPF invalido")
        return normalized


class StrictPatientUpdate(StrictPatientCreate):
    expected_version: int = Field(ge=1)


class ProfessionalIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    council_type: Literal["CRM", "CRP"]
    council_number: str = Field(min_length=2, max_length=20)
    council_region: str | None = Field(default="SP", max_length=5)
    specialty: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    commission_rate: Decimal = Field(default=Decimal("0.6000"), ge=0, le=1)


class ProfessionalUpdate(ProfessionalIn):
    expected_version: int = Field(ge=1)
    active: bool = True


class ServiceTypeIn(BaseModel):
    code: Literal["MEDICAL_EXAM", "PSYCHOTECHNICAL"]
    name: str = Field(min_length=2, max_length=100)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class AgendaRowIn(BaseModel):
    source_row: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=120)
    cpf: str | None = None
    birth_date: date | None = None
    scheduled_at: datetime
    service_code: Literal["MEDICAL_EXAM", "PSYCHOTECHNICAL"]
    renach: str | None = Field(default=None, max_length=20)
    process_type: str | None = Field(default=None, max_length=80)
    license_category: str | None = Field(default=None, max_length=10)
    exam_status: str | None = Field(default=None, max_length=30)
    medical_status: str | None = Field(default=None, max_length=30)
    psychological_status: str | None = Field(default=None, max_length=30)

    @field_validator("cpf")
    @classmethod
    def normalize_optional_cpf(cls, value):
        normalized = cpf_digits(value)
        return normalized if normalized and valid_cpf(normalized) else None


class AgendaImportIn(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_name: str = Field(min_length=1, max_length=255)
    agenda_date: date
    rows: list[AgendaRowIn] = Field(min_length=1, max_length=2000)


class ManualAppointmentIn(BaseModel):
    patient_id: int
    professional_id: int | None = None
    service_code: Literal["MEDICAL_EXAM", "PSYCHOTECHNICAL"]
    scheduled_at: datetime
    origin: Literal["RETURN", "WALK_IN"]
    renach: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class FinalizeIn(BaseModel):
    outcome: Literal["COMPLETED", "NO_SHOW", "TEMPORARILY_UNFIT"]
    rejection_reason: (
        Literal[
            "DOCUMENTATION_MISSING", "MEDICAL_EXAM_FAILED", "PSYCHOLOGICAL_EXAM_FAILED", "OTHER"
        ]
        | None
    ) = None
    missing_documents: bool = False
    observation: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_unfit(self):
        if self.outcome == "TEMPORARILY_UNFIT" and not (
            self.rejection_reason or (self.observation or "").strip()
        ):
            raise ValueError("Inapto temporario exige motivo ou observacao")
        return self


@router.get("/professionals")
def list_professionals(
    _: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
    search: str | None = Query(default=None, max_length=120),
) -> dict:
    statement = select(Professional).where(Professional.active.is_(True))
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Professional.name.ilike(term), Professional.council_number.like(term))
        )
    items = list(db.scalars(statement.order_by(Professional.name).limit(100)))
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "council_type": p.council_type,
                "council_number": p.council_number,
                "phone": p.phone,
                "email": p.email,
                "commission_rate": str(p.commission_rate),
                "specialty": p.specialty,
                "council_region": p.council_region,
                "active": p.active,
                "row_version": p.row_version,
            }
            for p in items
        ],
        "total": len(items),
    }


@router.get("/professionals/{professional_id}")
def get_professional(
    professional_id: int,
    _: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Professional, professional_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profissional nao encontrado")
    return {
        "id": item.id,
        "name": item.name,
        "council_type": item.council_type,
        "council_number": item.council_number,
        "council_region": item.council_region,
        "specialty": item.specialty,
        "phone": item.phone,
        "email": item.email,
        "commission_rate": str(item.commission_rate),
        "active": item.active,
        "row_version": item.row_version,
    }


@router.post("/professionals", status_code=status.HTTP_201_CREATED)
def create_professional(
    payload: ProfessionalIn,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.create", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    duplicate = db.scalar(
        select(Professional.id).where(
            Professional.council_type == payload.council_type,
            Professional.council_number == payload.council_number,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Conselho ja cadastrado")
    item = Professional(**payload.model_dump(), active=True)
    db.add(item)
    db.flush()
    result = {
        "id": item.id,
        **payload.model_dump(mode="json"),
        "active": True,
        "row_version": item.row_version,
    }
    audit(db, context, "create", "professionals", item.id, None, result)
    db.commit()
    return result


@router.put("/professionals/{professional_id}")
def update_professional(
    professional_id: int,
    payload: ProfessionalUpdate,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.write", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Professional, professional_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profissional nao encontrado")
    if item.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    before = {"row_version": item.row_version, "active": item.active}
    for key, value in payload.model_dump(exclude={"expected_version"}).items():
        setattr(item, key, value)
    item.row_version += 1
    result = {
        "id": item.id,
        **payload.model_dump(mode="json", exclude={"expected_version"}),
        "row_version": item.row_version,
    }
    audit(db, context, "update", "professionals", item.id, before, result)
    db.commit()
    return result


@router.delete("/professionals/{professional_id}")
def deactivate_professional(
    professional_id: int,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.write", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Professional, professional_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profissional nao encontrado")
    item.active = False
    audit(db, context, "deactivate", "professionals", item.id, None, {"active": False})
    db.commit()
    return {"id": item.id, "active": False}


@router.post("/patients", status_code=status.HTTP_201_CREATED)
def create_strict_patient(
    payload: StrictPatientCreate,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.create", "gerente", "atendente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    if db.scalar(select(Patient.id).where(Patient.cpf == payload.cpf)):
        raise HTTPException(status_code=409, detail="CPF ja cadastrado")
    patient = Patient(**payload.model_dump(), active=True)
    db.add(patient)
    db.flush()
    result = {"id": patient.id, **payload.model_dump(mode="json"), "legacy_incomplete": False}
    audit(db, context, "create", "patients", patient.id, None, result)
    db.commit()
    return result


def patient_operation_json(patient: Patient) -> dict:
    return {
        "id": patient.id,
        "name": patient.name,
        "cpf": patient.cpf,
        "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
        "phone": patient.phone,
        "email": patient.email,
        "address_json": patient.address_json,
        "gender": patient.gender,
        "marital_status": patient.marital_status,
        "process_type": patient.process_type,
        "observations": patient.observations,
        "active": patient.active,
        "row_version": patient.row_version,
        "legacy_incomplete": not all((patient.name, patient.birth_date, patient.cpf)),
    }


@router.get("/patients")
def list_operation_patients(
    _: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=10, le=100),
) -> dict:
    statement = select(Patient).where(Patient.active.is_(True))
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Patient.name.ilike(term), Patient.cpf.like(term), Patient.phone.like(term))
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    items = list(
        db.scalars(statement.order_by(Patient.name).offset((page - 1) * page_size).limit(page_size))
    )
    return {
        "items": [patient_operation_json(item) for item in items],
        "page": page,
        "pages": pages,
        "page_size": page_size,
        "total": total,
    }


@router.get("/patients/{patient_id}")
def get_operation_patient(
    patient_id: int,
    _: Annotated[
        AuthContext,
        Depends(require_permission("demographic.read", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Patient, patient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    return patient_operation_json(item)


@router.put("/patients/{patient_id}")
def update_operation_patient(
    patient_id: int,
    payload: StrictPatientUpdate,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.write", "gerente", "atendente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Patient, patient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    if item.row_version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Registro alterado por outro usuario")
    before = patient_operation_json(item)
    for key, value in payload.model_dump(exclude={"expected_version"}).items():
        setattr(item, key, value)
    item.row_version += 1
    result = patient_operation_json(item)
    audit(db, context, "update", "patients", item.id, before, result)
    db.commit()
    return result


@router.delete("/patients/{patient_id}")
def deactivate_patient(
    patient_id: int,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("demographic.write", "gerente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Patient, patient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado")
    item.active = False
    audit(db, context, "deactivate", "patients", item.id, None, {"active": False})
    db.commit()
    return {"id": item.id, "active": False}


@router.post("/service-types", status_code=status.HTTP_201_CREATED)
def upsert_service_type(
    payload: ServiceTypeIn,
    context: Annotated[AuthContext, Depends(require_csrf_permission("schedule.write", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.scalar(select(ServiceType).where(ServiceType.code == payload.code))
    if item:
        item.name, item.price, item.active = payload.name, payload.price, True
    else:
        item = ServiceType(**payload.model_dump(), active=True)
        db.add(item)
    db.flush()
    result = {"id": item.id, "code": item.code, "name": item.name, "price": str(item.price)}
    audit(db, context, "upsert", "service_types", item.id, None, result)
    db.commit()
    return result


def _source_key(digest: str, row: int, service_code: str) -> str:
    return hashlib.sha256(f"{digest}:{row}:{service_code}".encode()).hexdigest()[:40]


@router.post("/agenda/import", status_code=status.HTTP_201_CREATED)
def import_agenda(
    payload: AgendaImportIn,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("schedule.write", "gerente", "atendente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    existing = db.scalar(
        select(AgendaImportBatch).where(AgendaImportBatch.sha256 == payload.sha256)
    )
    if existing:
        return {
            "batch_id": existing.id,
            "status": existing.status,
            "row_count": existing.row_count,
            "idempotent": True,
        }
    batch = AgendaImportBatch(
        sha256=payload.sha256,
        original_name=payload.original_name,
        agenda_date=payload.agenda_date,
        status="IMPORTED",
        row_count=len(payload.rows),
        imported_by_id=context.user.id,
    )
    db.add(batch)
    db.flush()
    created = exceptions = 0
    for row in payload.rows:
        key = _source_key(payload.sha256, row.source_row, row.service_code)
        patient = db.scalar(select(Patient).where(Patient.cpf == row.cpf)) if row.cpf else None
        service_codes = [row.service_code]
        if row.exam_status is None and row.service_code == "MEDICAL_EXAM" and row.psychological_status:
            # A DETRAN row can carry both exam outcomes; the second service is
            # represented as a separate appointment for independent workflow/payment.
            service_codes.append("PSYCHOTECHNICAL")
        appointments = []
        row_status = "REQUIRES_REVIEW"
        if patient:
            for service_code in service_codes:
                service = db.scalar(select(ServiceType).where(
                    ServiceType.code == service_code, ServiceType.active.is_(True)))
                if not service:
                    continue
                appointment = Appointment(
                    patient_id=patient.id, exam_date=row.scheduled_at.date(),
                    scheduled_at=row.scheduled_at.replace(tzinfo=None), service_type_id=service.id,
                    renach=row.renach, process_type=row.process_type,
                    license_category=row.license_category,
                    exam_status=(row.medical_status if service_code == "MEDICAL_EXAM" else row.psychological_status) or row.exam_status,
                    status="aberto", operational_status="SCHEDULED", source_kind="DETRAN_PDF",
                    source_key=_source_key(payload.sha256, row.source_row, service_code),
                    created_by_id=context.user.id)
                db.add(appointment); db.flush(); appointments.append(appointment)
            if appointments:
                created += len(appointments)
                appointment = appointments[0]
                row_status = "CREATED"
            else:
                appointment = None
        else:
            exceptions += 1
            appointment = None
        db.add(
            AgendaImportRow(
                batch_id=batch.id,
                source_row=row.source_row,
                source_key=key,
                payload_json=row.model_dump(mode="json"),
                patient_id=patient.id if patient else None,
                appointment_id=appointment.id if appointment else None,
                status=row_status,
            )
        )
    result = {
        "batch_id": batch.id,
        "status": batch.status,
        "row_count": batch.row_count,
        "appointments_created": created,
        "requires_review": exceptions,
        "idempotent": False,
    }
    audit(db, context, "import", "agenda_import_batches", batch.id, None, result)
    db.commit()
    return result


@router.post("/agenda/{batch_id}/rollback")
def rollback_agenda(
    batch_id: int,
    context: Annotated[AuthContext, Depends(require_csrf_permission("schedule.cancel", "gerente"))],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    batch = db.get(AgendaImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote nao encontrado")
    if batch.status == "ROLLED_BACK":
        return {"batch_id": batch.id, "status": batch.status, "idempotent": True}
    appointment_ids = list(
        db.scalars(
            select(AgendaImportRow.appointment_id).where(
                AgendaImportRow.batch_id == batch.id, AgendaImportRow.appointment_id.is_not(None)
            )
        )
    )
    if appointment_ids and db.scalar(
        select(ClinicalDocument.id)
        .where(ClinicalDocument.appointment_id.in_(appointment_ids))
        .limit(1)
    ):
        raise HTTPException(
            status_code=409, detail="Lote possui documento clinico e nao pode ser revertido"
        )
    if appointment_ids:
        db.execute(delete(Appointment).where(Appointment.id.in_(appointment_ids)))
    for row in db.scalars(select(AgendaImportRow).where(AgendaImportRow.batch_id == batch.id)):
        row.appointment_id = None
        row.status = "ROLLED_BACK"
    batch.status = "ROLLED_BACK"
    batch.rolled_back_at = datetime.now(UTC).replace(tzinfo=None)
    batch.rolled_back_by_id = context.user.id
    audit(
        db,
        context,
        "rollback",
        "agenda_import_batches",
        batch.id,
        None,
        {"appointments_removed": len(appointment_ids)},
    )
    db.commit()
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "appointments_removed": len(appointment_ids),
        "idempotent": False,
    }


@router.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_manual_appointment(
    payload: ManualAppointmentIn,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("schedule.write", "gerente", "atendente"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    patient = db.get(Patient, payload.patient_id)
    service = db.scalar(
        select(ServiceType).where(
            ServiceType.code == payload.service_code, ServiceType.active.is_(True)
        )
    )
    if not patient or not service:
        raise HTTPException(status_code=422, detail="Paciente ou servico inexistente")
    professional = (
        db.get(Professional, payload.professional_id) if payload.professional_id else None
    )
    item = Appointment(
        patient_id=patient.id,
        exam_date=payload.scheduled_at.date(),
        scheduled_at=payload.scheduled_at.replace(tzinfo=None),
        service_type_id=service.id,
        doctor_id=professional.id if professional and professional.council_type == "CRM" else None,
        psychologist_id=professional.id
        if professional and professional.council_type == "CRP"
        else None,
        renach=payload.renach,
        notes=payload.notes,
        status="aberto",
        operational_status="SCHEDULED",
        source_kind=payload.origin,
        created_by_id=context.user.id,
    )
    db.add(item)
    db.flush()
    audit(db, context, "create", "appointments", item.id, None, {"origin": item.source_kind})
    db.commit()
    return {"id": item.id, "status": item.operational_status, "payment_status": "PENDING"}


@router.post("/appointments/{appointment_id}/finalize")
def finalize_appointment(
    appointment_id: int,
    payload: FinalizeIn,
    context: Annotated[
        AuthContext, Depends(require_csrf_permission("clinical_queue.write", "gerente", "medico"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    item = db.get(Appointment, appointment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    if item.operational_status not in {"SCHEDULED", "NO_SHOW", "TEMPORARILY_UNFIT"}:
        raise HTTPException(status_code=409, detail="Transicao de atendimento invalida")
    before = {"operational_status": item.operational_status}
    item.operational_status = payload.outcome
    item.rejection_reason = payload.rejection_reason
    item.missing_documents = payload.missing_documents
    item.operational_observation = payload.observation
    item.finalized_by_id = context.user.id
    item.completed_at = datetime.now(UTC).replace(tzinfo=None)
    item.status = (
        "concluido"
        if payload.outcome == "COMPLETED"
        else ("cancelado" if payload.outcome == "NO_SHOW" else "aberto")
    )
    item.result = "APTO" if payload.outcome == "COMPLETED" else payload.outcome
    item.workflow_status = (
        "CONCLUIDO_PAGAMENTO_INDEPENDENTE" if payload.outcome == "COMPLETED" else payload.outcome
    )
    audit(
        db,
        context,
        "finalize",
        "appointments",
        item.id,
        before,
        {"operational_status": item.operational_status},
    )
    db.commit()
    return {
        "id": item.id,
        "status": item.operational_status,
        "payment_status": "INDEPENDENT",
        "document_allowed": payload.outcome == "COMPLETED",
    }
