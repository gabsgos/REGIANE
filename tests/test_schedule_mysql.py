"""Opt-in MySQL checks; only run against the named disposable QA database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.schedule import ExtraIn, PolicyIn, create_extra, set_weekday
from backend.app.db import workspace_scope  # noqa: F401
from backend.app.db.models import Appointment, AuthSession, Patient, Professional, ServiceType, User

URL = os.getenv('ABEL_TEST_MYSQL_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires disposable MySQL QA database')


def test_mysql_concurrent_last_slot():
    engine = create_engine(URL, pool_size=4)
    assert engine.url.database == 'abelqa_schedule'
    assert engine.url.host == '127.0.0.1' and engine.url.port == 13307
    with Session(engine) as db:
        if db.scalar(select(ServiceType).where(ServiceType.code == 'MEDICAL_EXAM')) is None:
            db.add(ServiceType(code='MEDICAL_EXAM', name='QA medical service', price=100, workspace_id=1))
        actor = db.scalar(select(User).where(User.username == 'qa-capacity'))
        if actor is None:
            actor = User(username='qa-capacity', display_name='QA', workspace_id=1, active=True)
            db.add(actor)
            db.flush()
        patient = Patient(name='QA synthetic', workspace_id=1)
        professional = Professional(name='QA synthetic', council_type='CRM', council_number=uuid4().hex[:20], workspace_id=1)
        db.add_all([patient, professional])
        db.commit()
        actor_id, patient_id, professional_id = actor.id, patient.id, professional.id
        context = AuthContext(user=actor, session=AuthSession(), roles=frozenset({'gerente'}))
        db.info['workspace_id'] = 1
        set_weekday(professional_id, date(2026, 11, 17).weekday(), PolicyIn(extra_limit=1), context, db)
    barrier = Barrier(2)
    def reserve(_):
        with Session(engine) as db:
            db.info['workspace_id'] = 1
            context = AuthContext(user=User(id=actor_id, workspace_id=1), session=AuthSession(), roles=frozenset({'gerente'}))
            barrier.wait(timeout=10)
            try:
                create_extra(ExtraIn(patient_id=patient_id, professional_id=professional_id,
                    day=date(2026, 11, 17), service_code='MEDICAL_EXAM', reason='EXTRA_AUTORIZADO',
                    idempotency_key=uuid4()), context, db)
                return 201
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [201, 409]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.doctor_id == professional_id)) == 1
    engine.dispose()
