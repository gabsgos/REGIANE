from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, Integer, MetaData, create_engine, func, select, update
from sqlalchemy.orm import Session

from backend.app.db import workspace_scope  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.models import Appointment, Patient, Payment, Professional


@pytest.fixture
def database():
    engine = create_engine('sqlite://')
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for column in copied.primary_key:
            if isinstance(column.type, BigInteger):
                column.type = Integer()
    metadata.create_all(engine)
    with Session(engine) as db:
        for workspace in (1, 2):
            db.add(Patient(id=workspace, name='Paciente', workspace_id=workspace))
            db.add(Professional(id=workspace, name='Profissional', council_type='CRM',
                                council_number=str(workspace), workspace_id=workspace))
        db.flush()
        for workspace in (1, 2):
            db.add(Appointment(id=workspace, patient_id=workspace, doctor_id=workspace,
                               exam_date=date(2026, 11, 17), workspace_id=workspace))
            db.add(Payment(id=workspace, appointment_id=workspace, total_amount=100,
                           workspace_id=workspace))
        db.commit()
    yield engine
    engine.dispose()


def test_queries_get_aggregates_and_bulk_updates_are_scoped(database):
    with Session(database) as db:
        db.info['workspace_id'] = 1
        assert db.get(Patient, 2) is None
        assert [p.id for p in db.scalars(select(Patient))] == [1]
        assert db.scalar(select(func.sum(Payment.total_amount))) == 100
        result = db.execute(update(Patient).where(Patient.id == 2).values(name='alterado'))
        assert result.rowcount == 0
        db.commit()
    with Session(database) as db:
        assert db.get(Patient, 2).name == 'Paciente'


def test_new_rows_inherit_authenticated_workspace(database):
    with Session(database) as db:
        db.info['workspace_id'] = 2
        patient = Patient(name='Novo')
        db.add(patient)
        db.flush()
        assert patient.workspace_id == 2


def test_cannot_link_foreign_patient_to_own_appointment(database):
    with Session(database) as db:
        db.info['workspace_id'] = 1
        db.add(Appointment(patient_id=2, doctor_id=1, exam_date=date(2026, 11, 17)))
        with pytest.raises(HTTPException, match='outro workspace'):
            db.flush()


def test_cannot_supply_another_workspace(database):
    with Session(database) as db:
        db.info['workspace_id'] = 1
        db.add(Patient(name='Invasao', workspace_id=2))
        with pytest.raises(HTTPException, match='Workspace invalido'):
            db.flush()
