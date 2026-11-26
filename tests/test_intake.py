from datetime import datetime
from uuid import UUID

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.operations import IntakeIn, create_intake
from backend.app.db.models import (
    Appointment,
    AuthSession,
    OperationIntake,
    Patient,
    Professional,
    ServiceType,
    User,
)
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

pytest_plugins = ("tests.test_workspace_scope",)

KEY = UUID("7b488b2e-2240-466f-a1f0-fd91230e8051")


@pytest.fixture
def intake_db(database):
    with Session(database) as db:
        db.info["workspace_id"] = 1
        db.add_all(
            [
                Patient(
                    id=3,
                    workspace_id=1,
                    name="Paciente Existente",
                    cpf="52998224725",
                    phone="111111111",
                ),
                Professional(
                    id=3,
                    workspace_id=1,
                    name="Psicologa",
                    council_type="CRP",
                    council_number="CRP-TESTE",
                ),
                ServiceType(
                    id=1,
                    workspace_id=1,
                    code="MEDICAL_EXAM",
                    name="Exame medico",
                    price=100,
                ),
                ServiceType(
                    id=2,
                    workspace_id=1,
                    code="PSYCHOTECHNICAL",
                    name="Exame psicotecnico",
                    price=150,
                ),
                User(
                    id=1,
                    workspace_id=1,
                    username="gestor-intake",
                    display_name="Gestor",
                    password_hash="teste",
                ),
            ]
        )
        db.commit()
        yield db


def context():
    return AuthContext(
        user=User(id=1, workspace_id=1),
        session=AuthSession(),
        roles=frozenset({"gerente"}),
    )


def payload(*, key=KEY, cpf="52998224725", name="Paciente Existente"):
    return IntakeIn.model_validate(
        {
            "source": "DETRAN_PDF",
            "idempotency_key": str(key),
            "patient": {
                "name": name,
                "cpf": cpf,
                "birth_date": "1990-01-01",
                "phone": "22999999999",
            },
            "services": [
                {
                    "service_code": "MEDICAL_EXAM",
                    "professional_id": 1,
                    "scheduled_at": "2026-11-25T08:00:00-03:00",
                },
                {
                    "service_code": "PSYCHOTECHNICAL",
                    "professional_id": 3,
                    "scheduled_at": "2026-11-25T08:30:00-03:00",
                },
            ],
        }
    )


def test_intake_reuses_patient_and_creates_two_independent_appointments(intake_db):
    result = create_intake(payload(), context(), intake_db)

    assert result.patient_id == 3
    assert result.patient_created is False
    assert [item.service_code for item in result.appointments] == [
        "MEDICAL_EXAM",
        "PSYCHOTECHNICAL",
    ]
    assert result.appointments[0].scheduled_at == datetime(2026, 11, 25, 8)
    assert intake_db.get(Patient, 3).phone == "111111111"


def test_intake_retry_is_idempotent(intake_db):
    first = create_intake(payload(), context(), intake_db)
    second = create_intake(payload(), context(), intake_db)

    assert second.idempotent is True
    assert [item.id for item in second.appointments] == [item.id for item in first.appointments]
    assert all(item.created is False for item in second.appointments)
    assert intake_db.scalar(select(func.count()).select_from(OperationIntake)) == 1
    assert intake_db.scalar(select(func.count()).select_from(Appointment)) == 3


def test_intake_without_cpf_creates_patient_once(intake_db):
    request = payload(cpf=None, name="Paciente Sem CPF")
    first = create_intake(request, context(), intake_db)
    second = create_intake(request, context(), intake_db)

    assert first.patient_created is True
    assert second.patient_id == first.patient_id
    assert second.idempotent is True


def test_intake_rejects_key_reuse_with_different_payload(intake_db):
    create_intake(payload(), context(), intake_db)

    with pytest.raises(HTTPException, match="outros dados"):
        create_intake(payload(name="Outro Nome"), context(), intake_db)


def test_intake_rolls_back_when_professional_is_incompatible(intake_db):
    request = payload(cpf=None, name="Paciente para rollback")
    request.services[1].professional_id = 1

    with pytest.raises(HTTPException, match="incompativel"):
        create_intake(request, context(), intake_db)
    intake_db.rollback()

    assert intake_db.scalar(select(func.count()).select_from(OperationIntake)) == 0
    assert (
        intake_db.scalar(
            select(func.count())
            .select_from(Patient)
            .where(Patient.name == "Paciente para rollback")
        )
        == 0
    )
