from datetime import date, datetime

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.operations import return_eligible_appointments
from backend.app.db.models import Appointment, AuthSession, ServiceType, User
from fastapi import HTTPException
from sqlalchemy.orm import Session

pytest_plugins = ("tests.test_workspace_scope",)


@pytest.fixture
def return_db(database):
    with Session(database) as db:
        db.info["workspace_id"] = 1
        db.add(
            ServiceType(id=1, workspace_id=1, code="MEDICAL_EXAM", name="Exame medico", price=100)
        )
        eligible = db.get(Appointment, 1)
        eligible.service_type_id = 1
        eligible.doctor_id = 1
        eligible.status = "aberto"
        eligible.operational_status = "NO_SHOW"
        eligible.scheduled_at = datetime(2026, 11, 20, 8)
        db.add(
            Appointment(
                id=3,
                workspace_id=1,
                patient_id=1,
                doctor_id=1,
                service_type_id=1,
                exam_date=date(2026, 11, 21),
                scheduled_at=datetime(2026, 11, 21, 8),
                status="concluido",
                operational_status="COMPLETED",
            )
        )
        db.commit()
        yield db


def context(*roles, professional_id=None):
    return AuthContext(
        user=User(id=10, workspace_id=1, professional_id=professional_id),
        session=AuthSession(),
        roles=frozenset(roles),
    )


def test_endpoint_returns_only_unfinished_eligible_appointment(return_db):
    result = return_eligible_appointments(
        1, context("gerente"), return_db, service_code="MEDICAL_EXAM", professional_id=None
    )

    assert [item.id for item in result] == [1]
    assert result[0].professional_id == 1


def test_active_return_removes_previous_appointment_from_eligibility(return_db):
    return_db.add(
        Appointment(
            id=4,
            workspace_id=1,
            patient_id=1,
            doctor_id=1,
            service_type_id=1,
            exam_date=date(2026, 11, 26),
            scheduled_at=datetime(2026, 11, 26, 8),
            previous_appointment_id=1,
            status="aberto",
            operational_status="SCHEDULED",
        )
    )
    return_db.commit()

    assert (
        return_eligible_appointments(
            1, context("gerente"), return_db, service_code=None, professional_id=None
        )
        == []
    )


def test_unassigned_professional_cannot_probe_return_history(return_db):
    with pytest.raises(HTTPException, match="Paciente nao encontrado"):
        return_eligible_appointments(
            1,
            context("medico", professional_id=99),
            return_db,
            service_code=None,
            professional_id=None,
        )
