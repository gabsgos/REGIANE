"""Workspace-scoped daily extras and psychotechnical groups."""
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext, require_csrf_permission, require_permission
from backend.app.api.routes.clinical import appointment_scope, audit
from backend.app.db.models import (Appointment, Patient, Payment, Professional,
    ProfessionalDayOverride, ProfessionalScheduleRule, ScheduleSession, ServiceType)
from backend.app.db.session import get_db_session

router = APIRouter(prefix='/operations/schedule', tags=['agenda-capacidade'])
Reader = Annotated[AuthContext, Depends(require_permission('schedule.read', 'gerente', 'atendente', 'medico', 'psicologo'))]
Writer = Annotated[AuthContext, Depends(require_csrf_permission('schedule.write', 'gerente', 'atendente'))]
Manager = Annotated[AuthContext, Depends(require_csrf_permission(
    'schedule.manage_availability', 'gerente', 'atendente'))]
Database = Annotated[Session, Depends(get_db_session)]


class PolicyIn(BaseModel):
    limit_mode: Literal['LIMITED', 'UNLIMITED'] = 'LIMITED'
    extra_limit: int | None = Field(default=0, ge=0, le=10000)
    closed: bool = False
    start_time: time | None = None
    end_time: time | None = None
    reason: str = Field(default='Regra da agenda', min_length=3, max_length=255)

    @model_validator(mode='after')
    def valid_limit(self):
        if self.limit_mode == 'LIMITED' and self.extra_limit is None:
            raise ValueError('Informe o limite')
        if self.limit_mode == 'UNLIMITED':
            self.extra_limit = None
        if bool(self.start_time) != bool(self.end_time) or (self.start_time and self.end_time <= self.start_time):
            raise ValueError('Jornada invalida')
        return self


class ExtraIn(BaseModel):
    patient_id: int = Field(gt=0)
    professional_id: int = Field(gt=0)
    day: date
    service_code: Literal['MEDICAL_EXAM', 'PSYCHOTECHNICAL']
    reason: Literal['EXTRA_RETORNO', 'EXTRA_FALTA_ANTERIOR', 'EXTRA_AUTORIZADO']
    arrival_time: time | None = None
    notes: str | None = Field(default=None, max_length=1000)
    renach: str | None = Field(default=None, max_length=20)
    previous_appointment_id: int | None = None
    session_id: int | None = None
    idempotency_key: UUID


class GroupIn(BaseModel):
    professional_id: int = Field(gt=0)
    starts_at: datetime
    capacity: int = Field(ge=1, le=1000)


class AvailabilitySlotOut(BaseModel):
    time: time
    available: bool


class AvailabilityDayOut(BaseModel):
    day: date
    source: str
    closed: bool
    limit_mode: str
    extra_limit: int | None
    used: int
    available: int | None
    start_time: time | None
    end_time: time | None
    slots: list[AvailabilitySlotOut]


class AvailabilityOut(BaseModel):
    professional_id: int
    date_from: date
    date_to: date
    days: list[AvailabilityDayOut]


def local_datetime(value):
    return value.astimezone(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None) if value.tzinfo else value


def professional_for(db, professional_id, context, lock=False):
    if context.roles.intersection({'medico', 'psicologo'}) and 'gerente' not in context.roles:
        if context.user.professional_id != professional_id:
            raise HTTPException(404, 'Profissional nao encontrado')
    statement = select(Professional).where(Professional.id == professional_id, Professional.active.is_(True))
    professional = db.scalar(statement.with_for_update() if lock else statement)
    if not professional or not professional.council_number.strip():
        raise HTTPException(404, 'Profissional nao encontrado')
    return professional


def policy_from(weekly, override):
    rule = override or weekly
    start_time = override.start_time if override and override.start_time else (
        weekly.start_time if weekly else None)
    end_time = override.end_time if override and override.end_time else (
        weekly.end_time if weekly else None)
    return {
        'source': 'DATE' if override else ('WEEKDAY' if weekly else 'DEFAULT'),
        'closed': rule.closed if rule else False,
        'limit_mode': rule.limit_mode if rule else 'LIMITED',
        'extra_limit': rule.extra_limit if rule else 0,
        'start_time': start_time.isoformat() if start_time else None,
        'end_time': end_time.isoformat() if end_time else None,
    }


def policy_for(db, professional_id, day):
    override = db.scalar(select(ProfessionalDayOverride).where(
        ProfessionalDayOverride.professional_id == professional_id, ProfessionalDayOverride.day == day))
    weekly = db.scalar(select(ProfessionalScheduleRule).where(
        ProfessionalScheduleRule.professional_id == professional_id,
        ProfessionalScheduleRule.weekday == day.weekday()))
    return policy_from(weekly, override)


def slot_times(policy):
    if policy['closed'] or not policy['start_time'] or not policy['end_time']:
        return []
    start = datetime.combine(date.min, time.fromisoformat(policy['start_time']))
    end = datetime.combine(date.min, time.fromisoformat(policy['end_time']))
    total_seconds = int((end - start).total_seconds())
    count = policy['extra_limit'] if policy['limit_mode'] == 'LIMITED' else max(
        1, total_seconds // (30 * 60))
    if not count:
        return []
    return [(start + timedelta(seconds=(total_seconds * index) // count)).time()
            for index in range(count)]


def extra_count(db, professional_id, day, session_id=None):
    filters = [Appointment.exam_date == day,
        or_(Appointment.doctor_id == professional_id, Appointment.psychologist_id == professional_id),
        or_(Appointment.status != 'cancelado', Appointment.operational_status == 'NO_SHOW')]
    if session_id is None:
        filters.extend([Appointment.source_kind == 'EXTRA', Appointment.schedule_session_id.is_(None)])
    else:
        filters.append(Appointment.schedule_session_id == session_id)
    return db.scalar(select(func.count()).select_from(Appointment).where(*filters)) or 0


def return_state_eligible(item: Appointment, as_of: date) -> bool:
    if item.status in {'concluido', 'cancelado'}:
        return False
    if item.operational_status in {'NO_SHOW', 'TEMPORARILY_UNFIT'}:
        return True
    return item.exam_date <= as_of and item.operational_status in {
        'SCHEDULED', 'WAITING', 'IN_PROGRESS'}


def has_active_return(db: Session, appointment_id: int) -> bool:
    return bool(db.scalar(select(Appointment.id).where(
        Appointment.previous_appointment_id == appointment_id,
        Appointment.status != 'cancelado')))


@router.get('/capacity')
def capacity(day: date, professional_id: int, context: Reader, db: Database):
    professional_for(db, professional_id, context)
    policy = policy_for(db, professional_id, day)
    used = extra_count(db, professional_id, day)
    return {**policy, 'used': used, 'available': None if policy['limit_mode'] == 'UNLIMITED'
            else max(0, policy['extra_limit'] - used)}


@router.get('/professionals/{professional_id}/availability', response_model=AvailabilityOut)
def availability(
    professional_id: int,
    date_from: date,
    date_to: date,
    context: Reader,
    db: Database,
):
    if date_to < date_from or (date_to - date_from).days > 92:
        raise HTTPException(422, 'Periodo de disponibilidade invalido')
    professional_for(db, professional_id, context)
    weekly = {
        item.weekday: item
        for item in db.scalars(select(ProfessionalScheduleRule).where(
            ProfessionalScheduleRule.professional_id == professional_id))
    }
    overrides = {
        item.day: item
        for item in db.scalars(select(ProfessionalDayOverride).where(
            ProfessionalDayOverride.professional_id == professional_id,
            ProfessionalDayOverride.day >= date_from,
            ProfessionalDayOverride.day <= date_to))
    }
    scheduled = list(db.scalars(select(Appointment).where(
        Appointment.exam_date >= date_from,
        Appointment.exam_date <= date_to,
        or_(Appointment.doctor_id == professional_id,
            Appointment.psychologist_id == professional_id),
        Appointment.schedule_session_id.is_(None),
        Appointment.scheduled_at.is_not(None),
        or_(Appointment.status != 'cancelado', Appointment.operational_status == 'NO_SHOW'))))
    used_by_day: dict[date, int] = {}
    occupied_by_day: dict[date, set[time]] = {}
    for item in scheduled:
        occupied_by_day.setdefault(item.exam_date, set()).add(item.scheduled_at.time())
        if item.source_kind == 'EXTRA':
            used_by_day[item.exam_date] = used_by_day.get(item.exam_date, 0) + 1

    days = []
    current = date_from
    while current <= date_to:
        policy = policy_from(weekly.get(current.weekday()), overrides.get(current))
        used = used_by_day.get(current, 0)
        available_count = None if policy['limit_mode'] == 'UNLIMITED' else max(
            0, policy['extra_limit'] - used)
        occupied = occupied_by_day.get(current, set())
        slots = []
        remaining = available_count
        for slot in slot_times(policy):
            free = slot not in occupied and (remaining is None or remaining > 0)
            slots.append(AvailabilitySlotOut(time=slot, available=free))
            if free and remaining is not None:
                remaining -= 1
        days.append(AvailabilityDayOut(
            day=current,
            source=policy['source'],
            closed=policy['closed'],
            limit_mode=policy['limit_mode'],
            extra_limit=policy['extra_limit'],
            used=used,
            available=sum(1 for slot in slots if slot.available)
            if available_count is not None else None,
            start_time=time.fromisoformat(policy['start_time']) if policy['start_time'] else None,
            end_time=time.fromisoformat(policy['end_time']) if policy['end_time'] else None,
            slots=slots,
        ))
        current += timedelta(days=1)
    return AvailabilityOut(
        professional_id=professional_id,
        date_from=date_from,
        date_to=date_to,
        days=days,
    )


@router.put('/professionals/{professional_id}/weekdays/{weekday}')
def set_weekday(professional_id: int, weekday: int, payload: PolicyIn, context: Manager, db: Database):
    if weekday not in range(7):
        raise HTTPException(422, 'Dia da semana invalido')
    professional_for(db, professional_id, context, lock=True)
    item = db.scalar(select(ProfessionalScheduleRule).where(
        ProfessionalScheduleRule.professional_id == professional_id, ProfessionalScheduleRule.weekday == weekday))
    if item is None:
        item = ProfessionalScheduleRule(professional_id=professional_id, weekday=weekday)
        db.add(item)
    for field in ('limit_mode', 'extra_limit', 'closed', 'start_time', 'end_time'):
        setattr(item, field, getattr(payload, field))
    db.flush()
    audit(db, context, 'set_weekday', 'schedule_rules', item.id, None, payload.model_dump(mode='json'))
    db.commit()
    return {'id': item.id}


@router.put('/professionals/{professional_id}/dates/{day}')
def set_date(professional_id: int, day: date, payload: PolicyIn, context: Manager, db: Database):
    professional_for(db, professional_id, context, lock=True)
    item = db.scalar(select(ProfessionalDayOverride).where(
        ProfessionalDayOverride.professional_id == professional_id, ProfessionalDayOverride.day == day))
    if item is None:
        item = ProfessionalDayOverride(professional_id=professional_id, day=day)
        db.add(item)
    for field in ('limit_mode', 'extra_limit', 'closed', 'start_time', 'end_time', 'reason'):
        setattr(item, field, getattr(payload, field))
    db.flush()
    audit(db, context, 'set_date', 'schedule_overrides', item.id, None, payload.model_dump(mode='json'))
    db.commit()
    return {'id': item.id}


@router.post('/groups', status_code=201)
def create_group(payload: GroupIn, context: Manager, db: Database):
    professional = professional_for(db, payload.professional_id, context, lock=True)
    if professional.council_type != 'CRP':
        raise HTTPException(422, 'Turma exige profissional CRP')
    item = ScheduleSession(professional_id=professional.id, starts_at=local_datetime(payload.starts_at),
                           capacity=payload.capacity, status='OPEN')
    db.add(item)
    db.flush()
    audit(db, context, 'create_group', 'schedule_sessions', item.id, None, payload.model_dump(mode='json'))
    db.commit()
    return {'id': item.id, 'capacity': item.capacity}


@router.get('/groups')
def list_groups(day: date, professional_id: int, context: Reader, db: Database):
    professional_for(db, professional_id, context)
    rows = db.scalars(select(ScheduleSession).where(ScheduleSession.professional_id == professional_id,
        func.date(ScheduleSession.starts_at) == day, ScheduleSession.status == 'OPEN')).all()
    return {'items': [{'id': row.id, 'starts_at': row.starts_at, 'capacity': row.capacity,
                      'used': extra_count(db, professional_id, day, row.id)} for row in rows]}


@router.post('/extras', status_code=201)
def create_extra(payload: ExtraIn, context: Writer, db: Database):
    # Serializes capacity checks and writes even when a date has no override yet.
    professional = professional_for(db, payload.professional_id, context, lock=True)
    key = f'extra:{context.user.workspace_id}:{payload.idempotency_key}'
    existing = db.scalar(select(Appointment).where(Appointment.source_key == key))
    if existing:
        if (existing.doctor_id or existing.psychologist_id) != payload.professional_id:
            raise HTTPException(409, 'Chave de solicitacao ja utilizada com outro profissional')
        if (existing.patient_id, existing.exam_date, existing.service_type_id,
            existing.schedule_session_id) != (payload.patient_id, payload.day,
                db.scalar(select(ServiceType.id).where(ServiceType.code == payload.service_code)), payload.session_id):
            raise HTTPException(409, 'Chave de solicitacao ja utilizada com outros dados')
        return {'id': existing.id, 'idempotent': True}
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(404, 'Paciente nao encontrado')
    expected = 'PSYCHOTECHNICAL' if professional.council_type == 'CRP' else 'MEDICAL_EXAM'
    service = db.scalar(select(ServiceType).where(ServiceType.code == payload.service_code, ServiceType.active.is_(True)))
    if not service or payload.service_code != expected:
        raise HTTPException(422, 'Exame incompativel com o profissional')
    policy = policy_for(db, professional.id, payload.day)
    if policy['closed']:
        raise HTTPException(409, 'Data fechada')
    starts_at = datetime.combine(payload.day, payload.arrival_time) if payload.arrival_time else None
    if not payload.session_id and policy['start_time']:
        if not payload.arrival_time:
            raise HTTPException(422, detail={
                'code': 'SLOT_REQUIRED', 'message': 'Selecione um horario disponivel'})
        if payload.arrival_time not in slot_times(policy):
            raise HTTPException(422, detail={
                'code': 'SLOT_OUTSIDE_AVAILABILITY',
                'message': 'Horario fora dos slots do profissional'})
    if not payload.session_id and starts_at and db.scalar(select(Appointment.id).where(
        Appointment.scheduled_at == starts_at,
        or_(Appointment.doctor_id == professional.id,
            Appointment.psychologist_id == professional.id),
        Appointment.schedule_session_id.is_(None),
        or_(Appointment.status != 'cancelado', Appointment.operational_status == 'NO_SHOW'))):
        raise HTTPException(409, detail={
            'code': 'SLOT_UNAVAILABLE', 'message': 'Horario ja ocupado'})
    if payload.session_id:
        group = db.get(ScheduleSession, payload.session_id)
        if not group or group.status != 'OPEN' or group.professional_id != professional.id or group.starts_at.date() != payload.day or expected != 'PSYCHOTECHNICAL':
            raise HTTPException(422, 'Turma incompativel')
        if extra_count(db, professional.id, payload.day, group.id) >= group.capacity:
            raise HTTPException(409, 'Turma lotada')
        starts_at = group.starts_at
    elif policy['limit_mode'] == 'LIMITED' and extra_count(db, professional.id, payload.day) >= policy['extra_limit']:
        raise HTTPException(409, detail={
            'code': 'CAPACITY_EXHAUSTED',
            'message': 'Limite de encaixes atingido; solicite configuracao ao gestor'})
    if payload.previous_appointment_id:
        previous = db.get(Appointment, payload.previous_appointment_id)
        if (not previous or previous.patient_id != payload.patient_id
                or previous.service_type_id != service.id
                or not return_state_eligible(previous, payload.day)
                or has_active_return(db, previous.id)):
            raise HTTPException(422, detail={
                'code': 'PREVIOUS_APPOINTMENT_NOT_ELIGIBLE',
                'message': 'Atendimento anterior nao e elegivel para retorno'})
    item = Appointment(patient_id=payload.patient_id, exam_date=payload.day, scheduled_at=starts_at,
        doctor_id=professional.id if expected == 'MEDICAL_EXAM' else None,
        psychologist_id=professional.id if expected == 'PSYCHOTECHNICAL' else None,
        service_type_id=service.id, source_kind='EXTRA', source_key=key,
        booking_kind='PSICOTECNICO_GRUPO' if payload.session_id else payload.reason,
        schedule_session_id=payload.session_id, previous_appointment_id=payload.previous_appointment_id,
        status='aberto', operational_status='SCHEDULED', notes=payload.notes, renach=payload.renach,
        created_by_id=context.user.id)
    db.add(item)
    db.flush()
    audit(db, context, 'create_extra', 'appointments', item.id, None,
          {'policy': policy, 'reason': payload.reason, 'session_id': payload.session_id})
    db.commit()
    return {'id': item.id, 'idempotent': False}


@router.post('/extras/{appointment_id}/cancel')
def cancel_extra(appointment_id: int, context: Writer, db: Database):
    item = db.scalar(appointment_scope(select(Appointment).where(Appointment.id == appointment_id).with_for_update(), context))
    if not item or item.source_kind != 'EXTRA':
        raise HTTPException(404, 'Encaixe nao encontrado')
    professional_for(db, item.doctor_id or item.psychologist_id, context, lock=True)
    if item.operational_status != 'SCHEDULED' or db.scalar(select(Payment.id).where(Payment.appointment_id == item.id, Payment.status == 'pago')):
        raise HTTPException(409, 'Atendimento iniciado ou pago nao pode ser cancelado')
    item.status = 'cancelado'
    item.operational_status = 'CANCELLED'
    audit(db, context, 'cancel_extra', 'appointments', item.id, None, {'status': 'CANCELLED'})
    db.commit()
    return {'id': item.id, 'status': 'CANCELLED'}


@router.post('/appointments/{appointment_id}/arrival')
def register_arrival(appointment_id: int, context: Writer, db: Database):
    return update_queue(appointment_id, 'SCHEDULED', 'WAITING', context, db)


@router.post('/appointments/{appointment_id}/start')
def start_exam(appointment_id: int, context: Annotated[AuthContext, Depends(
    require_csrf_permission('clinical_queue.write', 'gerente', 'medico', 'psicologo')
)], db: Database):
    return update_queue(appointment_id, 'WAITING', 'IN_PROGRESS', context, db)


def update_queue(appointment_id, expected, target, context, db):
    item = db.scalar(appointment_scope(select(Appointment).where(
        Appointment.id == appointment_id).with_for_update(), context))
    if not item:
        raise HTTPException(404, 'Atendimento nao encontrado')
    allowed_roles = {'gerente', 'atendente'} if target == 'WAITING' else {'gerente', 'medico', 'psicologo'}
    if not context.roles & allowed_roles:
        raise HTTPException(403, 'Acao indisponivel para este perfil')
    if item.exam_date != datetime.now(ZoneInfo('America/Sao_Paulo')).date() or item.status != 'aberto':
        raise HTTPException(409, 'A fila aceita apenas atendimentos em aberto do dia')
    before = item.operational_status
    if before == target:
        return {'id': item.id, 'status': before}
    if before != expected:
        raise HTTPException(409, 'Transicao de fila invalida')
    item.operational_status = target
    audit(db, context, 'update_queue', 'appointments', item.id,
          {'operational_status': before}, {'operational_status': target})
    db.commit()
    return {'id': item.id, 'status': target}
