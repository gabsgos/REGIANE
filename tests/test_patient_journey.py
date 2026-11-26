from datetime import date, datetime

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.operations import get_patient_journey
from backend.app.db.models import (
    Appointment,
    AuthSession,
    ClinicalDocument,
    Payment,
    Professional,
    ServiceType,
    User,
)
from fastapi import HTTPException
from sqlalchemy.orm import Session

pytest_plugins = ("tests.test_workspace_scope",)


@pytest.fixture
def journey_db(database):
    with Session(database) as db:
        db.info["workspace_id"] = 1
        db.add(
            ServiceType(
                id=1,
                workspace_id=1,
                code="MEDICAL_EXAM",
                name="Exame medico",
                price=100,
            )
        )
        db.add(
            Professional(
                id=3,
                workspace_id=1,
                name="Outro medico",
                council_type="CRM",
                council_number="CRM-OUTRO",
            )
        )
        current = db.get(Appointment, 1)
        current.service_type_id = 1
        current.scheduled_at = datetime(2020, 1, 1, 8)
        payment = db.get(Payment, 1)
        payment.status = "pago"
        payment.paid_at = datetime(2020, 1, 1, 9)
        db.add_all(
            [
                Appointment(
                    id=3,
                    workspace_id=1,
                    patient_id=1,
                    doctor_id=1,
                    service_type_id=1,
                    exam_date=date(2099, 1, 1),
                    scheduled_at=datetime(2099, 1, 1, 8),
                    source_kind="EXTRA",
                    booking_kind="EXTRA_RETORNO",
                ),
                Appointment(
                    id=4,
                    workspace_id=1,
                    patient_id=1,
                    doctor_id=3,
                    service_type_id=1,
                    exam_date=date(2020, 2, 1),
                    scheduled_at=datetime(2020, 2, 1, 8),
                    source_kind="MANUAL",
                    booking_kind="MANUAL",
                ),
                ClinicalDocument(
                    id=1,
                    workspace_id=1,
                    appointment_id=1,
                    document_type="RENACH",
                    storage_key="synthetic.pdf",
                    original_name="renach-sintetico.pdf",
                    media_type="application/pdf",
                    size_bytes=100,
                    sha256="0" * 64,
                    version=1,
                    uploaded_by_id=1,
                    active=True,
                    workflow_status="PDF_AUTENTICADO",
                ),
            ]
        )
        db.commit()
        yield db


def context(*roles, professional_id=None):
    return AuthContext(
        user=User(id=10, workspace_id=1, professional_id=professional_id),
        session=AuthSession(),
        roles=frozenset(roles),
    )


def test_journey_returns_history_payment_document_and_future_booking(journey_db):
    result = get_patient_journey(1, context("gerente"), journey_db, 50)

    assert result.total_appointments == 2
    assert result.total_future_bookings == 1
    assert [item.id for item in result.future_bookings] == [3]
    current = next(item for item in result.appointments if item.id == 1)
    assert current.payment.status == "pago"
    assert current.documents[0].document_type == "RENACH"


def test_professional_journey_is_limited_to_assigned_appointments(journey_db):
    result = get_patient_journey(1, context("medico", professional_id=1), journey_db, 50)

    assert [item.id for item in result.appointments] == [1]
    assert [item.id for item in result.future_bookings] == [3]


def test_unassigned_professional_cannot_probe_patient_journey(journey_db):
    with pytest.raises(HTTPException, match="Paciente nao encontrado"):
        get_patient_journey(1, context("medico", professional_id=99), journey_db, 50)


def test_journey_does_not_cross_workspace(journey_db):
    with pytest.raises(HTTPException, match="Paciente nao encontrado"):
        get_patient_journey(2, context("gerente"), journey_db, 50)
