from datetime import datetime

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.documents import can_authenticate_document
from backend.app.api.routes.operations import FinalizeIn, finalize_appointment
from backend.app.db.models import Appointment, AuthSession, ClinicalDocument, User
from fastapi import HTTPException
from sqlalchemy.orm import Session

pytest_plugins = ("tests.test_workspace_scope",)


@pytest.fixture
def renach_db(database):
    with Session(database) as db:
        db.info["workspace_id"] = 1
        appointment = db.get(Appointment, 1)
        appointment.operational_status = "IN_PROGRESS"
        appointment.status = "aberto"
        appointment.scheduled_at = datetime(2026, 11, 25, 8)
        db.commit()
        yield db


def context():
    return AuthContext(
        user=User(id=1, workspace_id=1, professional_id=1),
        session=AuthSession(),
        roles=frozenset({"medico"}),
    )


def document():
    return ClinicalDocument(
        workspace_id=1,
        appointment_id=1,
        document_type="RENACH",
        storage_key="renach-sintetico.pdf",
        original_name="renach.pdf",
        media_type="application/pdf",
        size_bytes=100,
        sha256="0" * 64,
        version=1,
        uploaded_by_id=1,
        active=True,
        workflow_status="PDF_AUTENTICADO",
    )


def test_open_appointment_accepts_renach_upload(renach_db):
    assert can_authenticate_document(renach_db, context(), renach_db.get(Appointment, 1)) is True


def test_completion_requires_authenticated_renach(renach_db):
    with pytest.raises(HTTPException) as error:
        finalize_appointment(1, FinalizeIn(outcome="COMPLETED"), context(), renach_db)

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "RENACH_REQUIRED"
    assert renach_db.get(Appointment, 1).operational_status == "IN_PROGRESS"


def test_authenticated_renach_allows_completion(renach_db):
    renach_db.add(document())
    renach_db.commit()

    result = finalize_appointment(1, FinalizeIn(outcome="COMPLETED"), context(), renach_db)

    assert result["status"] == "COMPLETED"
    assert result["renach_authenticated"] is True
    assert renach_db.get(Appointment, 1).status == "concluido"


def test_cancelled_appointment_does_not_accept_document(renach_db):
    appointment = renach_db.get(Appointment, 1)
    appointment.status = "cancelado"
    appointment.operational_status = "NO_SHOW"
    renach_db.commit()

    assert can_authenticate_document(renach_db, context(), appointment) is False
