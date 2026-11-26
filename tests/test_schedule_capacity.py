from datetime import date, datetime, time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.schedule import (ExtraIn, GroupIn, PolicyIn, capacity, cancel_extra,
    availability, create_extra, create_group, set_date, set_weekday)
from backend.app.db.models import Appointment, AuthSession, Professional, ServiceType, User
pytest_plugins = ("tests.test_workspace_scope",)

DAY = date(2026, 11, 17)


@pytest.fixture
def schedule_db(database):
    with Session(database) as db:
        db.add_all([ServiceType(id=1, code='MEDICAL_EXAM', name='Medico', price=100),
                    ServiceType(id=2, code='PSYCHOTECHNICAL', name='Psico', price=150),
                    Professional(id=3, name='Psico', council_type='CRP', council_number='123', workspace_id=1)])
        db.commit()
        db.info['workspace_id'] = 1
        yield db


def context():
    return AuthContext(user=User(id=1, username='gestor', display_name='Gestor', workspace_id=1),
                       session=AuthSession(), roles=frozenset({'gerente'}))


def extra(**changes):
    values = dict(patient_id=1, professional_id=1, day=DAY, service_code='MEDICAL_EXAM',
                  reason='EXTRA_AUTORIZADO', idempotency_key=uuid4())
    values.update(changes)
    return ExtraIn(**values)


def test_daily_limit_counts_completed_and_retry_is_idempotent(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=1), context(), db)
    request = extra()
    result = create_extra(request, context(), db)
    assert create_extra(request, context(), db)['id'] == result['id']
    item = db.get(Appointment, result['id'])
    item.status, item.operational_status = 'concluido', 'COMPLETED'
    db.commit()
    assert capacity(DAY, 1, context(), db)['available'] == 0
    with pytest.raises(HTTPException, match='Limite'):
        create_extra(extra(), context(), db)


def test_date_override_unlimited_and_closed_day(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=0), context(), db)
    set_date(1, DAY, PolicyIn(limit_mode='UNLIMITED', reason='Excecao'), context(), db)
    create_extra(extra(), context(), db)
    create_extra(extra(), context(), db)
    assert capacity(DAY, 1, context(), db)['available'] is None
    set_date(1, DAY, PolicyIn(closed=True, reason='Fechamento'), context(), db)
    with pytest.raises(HTTPException, match='fechada'):
        create_extra(extra(), context(), db)


def test_cancel_releases_slot_but_no_show_does_not(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=1), context(), db)
    result = create_extra(extra(), context(), db)
    cancel_extra(result['id'], context(), db)
    result = create_extra(extra(), context(), db)
    item = db.get(Appointment, result['id'])
    item.status, item.operational_status = 'cancelado', 'NO_SHOW'
    db.commit()
    assert capacity(DAY, 1, context(), db)['available'] == 0


def test_collective_group_has_independent_capacity_and_same_start(schedule_db):
    db = schedule_db
    group = create_group(GroupIn(professional_id=3, starts_at=datetime(2026, 11, 17, 9), capacity=2), context(), db)
    first = create_extra(extra(professional_id=3, service_code='PSYCHOTECHNICAL', session_id=group['id']), context(), db)
    second = create_extra(extra(professional_id=3, service_code='PSYCHOTECHNICAL', session_id=group['id']), context(), db)
    assert db.get(Appointment, first['id']).scheduled_at == db.get(Appointment, second['id']).scheduled_at
    with pytest.raises(HTTPException, match='lotada'):
        create_extra(extra(professional_id=3, service_code='PSYCHOTECHNICAL', session_id=group['id']), context(), db)


def test_wrong_exam_foreign_patient_and_professional_are_rejected(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=10), context(), db)
    for payload in [extra(patient_id=2), extra(professional_id=2), extra(service_code='PSYCHOTECHNICAL')]:
        with pytest.raises(HTTPException):
            create_extra(payload, context(), db)


def test_rebooking_preserves_old_occurrence(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=1), context(), db)
    old = db.get(Appointment, 1)
    old.operational_status, old.service_type_id = 'NO_SHOW', 1
    db.commit()
    result = create_extra(extra(previous_appointment_id=1, reason='EXTRA_FALTA_ANTERIOR'), context(), db)
    assert db.get(Appointment, result['id']).previous_appointment_id == 1
    assert db.get(Appointment, 1).operational_status == 'NO_SHOW'


def test_previous_appointment_must_be_eligible_and_have_no_active_return(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(extra_limit=5), context(), db)
    old = db.get(Appointment, 1)
    old.service_type_id = 1
    old.status, old.operational_status = 'concluido', 'COMPLETED'
    db.commit()
    with pytest.raises(HTTPException) as error:
        create_extra(extra(previous_appointment_id=1), context(), db)
    assert error.value.detail['code'] == 'PREVIOUS_APPOINTMENT_NOT_ELIGIBLE'

    old.status, old.operational_status = 'aberto', 'NO_SHOW'
    db.commit()
    create_extra(extra(previous_appointment_id=1), context(), db)
    with pytest.raises(HTTPException) as error:
        create_extra(extra(previous_appointment_id=1), context(), db)
    assert error.value.detail['code'] == 'PREVIOUS_APPOINTMENT_NOT_ELIGIBLE'


def test_availability_distributes_slots_and_rejects_collision(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(
        extra_limit=6, start_time=time(8), end_time=time(11)), context(), db)

    before = availability(1, DAY, DAY, context(), db).days[0]
    assert [slot.time for slot in before.slots] == [
        time(8), time(8, 30), time(9), time(9, 30), time(10), time(10, 30)]
    create_extra(extra(arrival_time=time(8)), context(), db)
    after = availability(1, DAY, DAY, context(), db).days[0]
    assert after.slots[0].available is False
    assert after.available == 5
    with pytest.raises(HTTPException) as error:
        create_extra(extra(arrival_time=time(8)), context(), db)
    assert error.value.detail['code'] == 'SLOT_UNAVAILABLE'


def test_date_override_can_replace_weekday_hours(schedule_db):
    db = schedule_db
    set_weekday(1, DAY.weekday(), PolicyIn(
        extra_limit=6, start_time=time(8), end_time=time(11)), context(), db)
    set_date(1, DAY, PolicyIn(
        extra_limit=2, start_time=time(9), end_time=time(10), reason='Horario especial'), context(), db)

    result = availability(1, DAY, DAY, context(), db).days[0]
    assert result.source == 'DATE'
    assert [slot.time for slot in result.slots] == [time(9), time(9, 30)]
