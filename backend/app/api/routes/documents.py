from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    AuthContext,
    require_csrf_permission,
    require_permission,
)
from backend.app.api.routes.clinical import audit
from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    ClinicalDocument,
    DocumentDelivery,
    Patient,
    Payment,
    Professional,
)
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/documents", tags=["documentos"])


def validate_pdf(data: bytes) -> int:
    if not data.startswith(b"%PDF-"):
        raise ValueError("assinatura PDF ausente")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, OSError) as exc:
        raise ValueError("PDF invalido") from exc
    if page_count < 1:
        raise ValueError("PDF sem paginas")
    return page_count


def can_access_appointment(context: AuthContext, appointment: Appointment) -> bool:
    if "gerente" in context.roles:
        return True
    if "medico" in context.roles and context.user.professional_id:
        return context.user.professional_id in {
            appointment.doctor_id,
            appointment.psychologist_id,
        }
    return False


def can_authenticate_document(
    db: Session, context: AuthContext, appointment: Appointment
) -> bool:
    if not context.user.professional_id:
        return False
    professional = db.get(Professional, context.user.professional_id)
    if (
        not professional
        or not professional.active
        or professional.council_type not in {"CRM", "CRP"}
    ):
        return False
    if "gerente" not in context.roles and context.user.professional_id not in {
        appointment.doctor_id,
        appointment.psychologist_id,
    }:
        return False
    paid = db.scalar(
        select(Payment.id).where(
            Payment.appointment_id == appointment.id, Payment.status == "pago"
        )
    )
    return bool(paid and appointment.status == "aberto")


def document_json(item: ClinicalDocument) -> dict:
    return {
        "id": item.id,
        "appointment_id": item.appointment_id,
        "document_type": item.document_type,
        "original_name": item.original_name,
        "media_type": item.media_type,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
        "version": item.version,
        "active": item.active,
        "workflow_status": item.workflow_status,
        "authenticated_at": item.authenticated_at.isoformat() if item.authenticated_at else None,
    }


class DeliveryCreate(BaseModel):
    appointment_id: int
    document_id: int | None = None
    channel: Literal["telefone", "whatsapp_manual", "email_manual", "presencial"]
    result: str = Field(min_length=2, max_length=40)


def masked_destination(patient: Patient, channel: str) -> str:
    if channel in {"telefone", "whatsapp_manual"}:
        return f"***{(patient.phone or '')[-4:]}" if patient.phone else "nao_informado"
    if channel == "email_manual" and patient.email and "@" in patient.email:
        local, domain = patient.email.split("@", 1)
        return f"{local[:1]}***@{domain}"
    return "presencial"


@router.post("/appointments/{appointment_id}", status_code=status.HTTP_201_CREATED)
async def upload_document(
    appointment_id: int,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("document.authenticate", "gerente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
    document_type: Annotated[str, Form(min_length=2, max_length=50)],
    file: Annotated[UploadFile, File()],
) -> dict:
    appointment = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if not appointment or not can_authenticate_document(db, context, appointment):
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    settings = get_settings()
    data = await file.read(settings.document_max_bytes + 1)
    if len(data) > settings.document_max_bytes:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite")
    try:
        page_count = validate_pdf(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage_root = Path(settings.document_storage_path).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    storage_key = f"{uuid.uuid4().hex}.pdf"
    target = (storage_root / storage_key).resolve()
    if target.parent != storage_root:
        raise HTTPException(status_code=500, detail="Caminho de armazenamento invalido")
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    current_version = (
        db.scalar(
            select(func.max(ClinicalDocument.version)).where(
                ClinicalDocument.appointment_id == appointment_id,
                ClinicalDocument.document_type == document_type,
            )
        )
        or 0
    )
    db.execute(
        update(ClinicalDocument)
        .where(
            ClinicalDocument.appointment_id == appointment_id,
            ClinicalDocument.document_type == document_type,
            ClinicalDocument.active.is_(True),
        )
        .values(active=False, updated_at=datetime.now(UTC).replace(tzinfo=None))
    )
    item = ClinicalDocument(
        appointment_id=appointment_id,
        document_type=document_type,
        storage_key=storage_key,
        original_name=(file.filename or "documento.pdf")[:255],
        media_type="application/pdf",
        size_bytes=len(data),
        sha256=digest,
        version=current_version + 1,
        uploaded_by_id=context.user.id,
        active=True,
        workflow_status="PDF_AUTENTICADO",
        authenticated_at=datetime.now(UTC).replace(tzinfo=None),
        authenticated_by_id=context.user.id,
    )
    try:
        db.add(item)
        db.flush()
        appointment.workflow_status = "PDF_AUTENTICADO"
        appointment.reanalysis_required = False
        appointment.operational_observation = None
        result = document_json(item)
        audit(
            db,
            context,
            "upload",
            "clinical_documents",
            item.id,
            None,
            {"sha256": digest, "size_bytes": len(data), "pages": page_count},
        )
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    return result


@router.get("/appointments/{appointment_id}")
def list_documents(
    appointment_id: int,
    context: Annotated[
        AuthContext, Depends(require_permission("document.read", "gerente", "medico"))
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or not can_access_appointment(context, appointment):
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    items = list(
        db.scalars(
            select(ClinicalDocument)
            .where(ClinicalDocument.appointment_id == appointment_id)
            .order_by(ClinicalDocument.document_type, ClinicalDocument.version.desc())
        )
    )
    return {"items": [document_json(item) for item in items]}


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    context: Annotated[
        AuthContext,
        Depends(require_permission("document.download", "gerente", "atendente", "medico")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> FileResponse:
    item = db.get(ClinicalDocument, document_id)
    if not item:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    appointment = db.get(Appointment, item.appointment_id)
    reception_final = "atendente" in context.roles and item.workflow_status in {
        "PDF_AUTENTICADO",
        "ENTREGUE",
        "EMENDADO",
    }
    if not appointment or not (can_access_appointment(context, appointment) or reception_final):
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    storage_root = Path(get_settings().document_storage_path).resolve()
    target = (storage_root / item.storage_key).resolve()
    if target.parent != storage_root or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual_hash != item.sha256:
        raise HTTPException(status_code=409, detail="Integridade do documento comprometida")
    audit(db, context, "download", "clinical_documents", item.id, None, {"sha256": actual_hash})
    db.commit()
    return FileResponse(
        target,
        media_type="application/pdf",
        filename=item.original_name,
        content_disposition_type="attachment",
    )


@router.get("/delivery/queue")
def delivery_queue(
    _: Annotated[
        AuthContext,
        Depends(require_permission("document.delivery_queue", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    document_rows = db.execute(
        select(ClinicalDocument, Appointment, Patient)
        .join(Appointment, Appointment.id == ClinicalDocument.appointment_id)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            ClinicalDocument.active.is_(True),
            ClinicalDocument.workflow_status.in_(("PDF_AUTENTICADO", "EMENDADO")),
        )
        .order_by(ClinicalDocument.authenticated_at, ClinicalDocument.id)
    ).all()
    reanalysis_rows = db.execute(
        select(Appointment, Patient)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(Appointment.reanalysis_required.is_(True))
        .order_by(Appointment.exam_date, Appointment.id)
    ).all()
    items = [
        {
            "kind": "document",
            "appointment_id": appointment.id,
            "document_id": document.id,
            "patient": patient.name,
            "phone": masked_destination(patient, "telefone"),
            "status": document.workflow_status,
            "observation": None,
        }
        for document, appointment, patient in document_rows
    ]
    items.extend(
        {
            "kind": "reanalysis",
            "appointment_id": appointment.id,
            "document_id": None,
            "patient": patient.name,
            "phone": masked_destination(patient, "telefone"),
            "status": "REANALISE_PENDENTE",
            "observation": appointment.operational_observation,
        }
        for appointment, patient in reanalysis_rows
    )
    return {"items": items, "total": len(items)}


@router.post("/delivery")
def register_manual_delivery(
    payload: DeliveryCreate,
    context: Annotated[
        AuthContext,
        Depends(require_csrf_permission("document.dispatch", "gerente", "atendente")),
    ],
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    appointment = db.get(Appointment, payload.appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    patient = db.get(Patient, appointment.patient_id)
    document = db.get(ClinicalDocument, payload.document_id) if payload.document_id else None
    if payload.document_id and (
        not document
        or document.appointment_id != appointment.id
        or document.workflow_status not in {"PDF_AUTENTICADO", "EMENDADO"}
    ):
        raise HTTPException(status_code=422, detail="Documento nao disponivel para entrega")
    if not document and not appointment.reanalysis_required:
        raise HTTPException(status_code=422, detail="Pendencia de reanalise inexistente")
    now = datetime.now(UTC).replace(tzinfo=None)
    delivery = DocumentDelivery(
        document_id=document.id if document else None,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        delivered_by_id=context.user.id,
        channel=payload.channel,
        destination_masked=masked_destination(patient, payload.channel),
        result=payload.result.strip(),
        delivered_at=now,
    )
    db.add(delivery)
    if document:
        document.workflow_status = "ENTREGUE"
        appointment.workflow_status = "ENTREGUE"
    db.flush()
    result = {
        "id": delivery.id,
        "appointment_id": appointment.id,
        "document_id": delivery.document_id,
        "channel": delivery.channel,
        "destination_masked": delivery.destination_masked,
        "result": delivery.result,
        "delivered_at": now.isoformat(),
    }
    audit(db, context, "manual_delivery", "document_deliveries", delivery.id, None, result)
    db.commit()
    return result
