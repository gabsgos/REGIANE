"""Exercise real HTTP auth routes against an isolated, disposable database."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, Integer, MetaData, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core.security import hash_password, token_digest
from backend.app.db.base import Base
from backend.app.db.models import Appointment, AuthSession, Patient, Permission, Professional, Role, RolePermission, User, UserRole, Workspace
from backend.app.db.session import get_db_session
from backend.app.main import create_app


@pytest.fixture
def auth_http():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        for column in copy.primary_key:
            if isinstance(column.type, BigInteger):
                column.type = Integer()
    metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Workspace(id=1, name='Teste', slug='teste'))
        db.add(User(id=1, workspace_id=1, username='gestor-http', display_name='Gestor Teste',
                    password_hash=hash_password('SenhaIsoladaParaTeste123!'), active=True,
                    must_reset_password=False))
        db.add(Role(id=1, name='gerente'))
        db.flush()
        db.add(UserRole(user_id=1, role_id=1))
        db.commit()
    app = create_app()
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db_session] = database
    with TestClient(app, base_url='https://testserver') as client:
        yield client, engine
    engine.dispose()


def login(client):
    return client.post('/abel/api/auth/login', json={
        'username': 'gestor-http', 'password': 'SenhaIsoladaParaTeste123!',
        'tab_id': 'tab-identificador-de-teste',
    })


def test_agenda_queue_requires_correct_role_csrf_and_workspace(auth_http):
    client, engine = auth_http
    password = hash_password('SenhaIsoladaParaTeste123!')
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    with Session(engine) as db:
        db.add(Workspace(id=2, name='Outro', slug='outro'))
        db.add_all([Role(id=2, name='atendente'), Role(id=3, name='medico')])
        db.add_all([
            Permission(id=1, key='schedule.write', resource='schedule', action='write', sensitivity='NORMAL'),
            Permission(id=2, key='clinical_queue.write', resource='clinical_worklist', action='write', sensitivity='HIGH_CLINICAL'),
        ])
        db.add_all([Patient(id=n, workspace_id=n, name='Paciente sintético') for n in (1, 2)])
        db.add(Professional(id=1, workspace_id=1, name='Teste CRM', council_type='CRM', council_number='123'))
        db.flush()
        db.add_all([User(id=n, workspace_id=1, username=name, display_name=name,
                         active=True, must_reset_password=False, password_hash=password,
                         professional_id=1 if n == 3 else None)
                    for n, name in ((2, 'recepcao-http'), (3, 'medico-http'))])
        db.add_all([Appointment(id=n, workspace_id=workspace, patient_id=workspace,
                                doctor_id=doctor, exam_date=today, status='aberto')
                    for n, workspace, doctor in ((1, 1, 1), (2, 2, None), (3, 1, None))])
        db.flush()
        db.add_all([UserRole(user_id=n, role_id=n) for n in (2, 3)])
        db.add_all([RolePermission(role_id=2, permission_id=1), RolePermission(role_id=3, permission_id=2)])
        db.commit()

    def enter(username):
        client.cookies.clear()
        response = client.post('/abel/api/auth/login', json={
            'username': username, 'password': 'SenhaIsoladaParaTeste123!',
            'tab_id': 'tab-identificador-de-teste',
        })
        assert response.status_code == 200
        return {'X-CSRF-Token': client.cookies.get('abel_csrf')}

    def queue(appointment_id, status, headers):
        return client.post(f'/abel/api/operations/schedule/appointments/{appointment_id}/{status}', headers=headers)

    headers = enter('recepcao-http')
    assert queue(1, 'arrival', {}).status_code == 403
    assert queue(2, 'arrival', headers).status_code == 404
    assert queue(1, 'arrival', headers).json()['status'] == 'WAITING'
    assert queue(1, 'start', headers).status_code == 403
    headers = enter('medico-http')
    assert queue(3, 'start', headers).status_code == 404
    assert queue(1, 'arrival', headers).status_code == 403
    assert queue(1, 'start', headers).json()['status'] == 'IN_PROGRESS'
    assert client.post('/abel/api/operations/appointments/1/finalize', headers=headers,
                       json={'outcome': 'COMPLETED'}).json()['status'] == 'COMPLETED'


def test_http_login_me_logout_rejects_replay(auth_http):
    client, engine = auth_http
    result = login(client)
    assert result.status_code == 200
    cookies = result.headers.get_list('set-cookie')
    assert len(cookies) == 2
    assert any('HttpOnly' in cookie and 'abel_session=' in cookie for cookie in cookies)
    assert all('SameSite=strict' in cookie for cookie in cookies)
    assert all('Max-Age' not in cookie for cookie in cookies)
    token = client.cookies.get('abel_session')
    me = client.get('/abel/api/auth/me')
    assert me.status_code == 200
    assert me.json()['roles'] == ['gerente']
    assert me.headers['cache-control'] == 'no-store'
    assert client.post('/abel/api/auth/logout').status_code == 204
    assert client.get('/abel/api/auth/me').status_code == 401
    client.cookies.set('abel_session', token)
    assert client.get('/abel/api/auth/me').status_code == 401
    with Session(engine) as db:
        record = db.scalar(select(AuthSession))
        assert record.token_hash == token_digest(token)
        assert record.expires_at - record.created_at == timedelta(hours=6)
        assert record.revoked_at is not None


@pytest.mark.parametrize('reason', ['idle', 'absolute', 'inactive', 'access_version'])
def test_http_rejects_expired_or_changed_access(auth_http, reason):
    client, engine = auth_http
    assert login(client).status_code == 200
    with Session(engine) as db:
        session = db.scalar(select(AuthSession))
        user = db.get(User, 1)
        now = datetime.now(UTC).replace(tzinfo=None)
        if reason == 'idle':
            session.last_seen_at = now - timedelta(minutes=16)
        elif reason == 'absolute':
            session.expires_at = now - timedelta(seconds=1)
        elif reason == 'inactive':
            user.active = False
        else:
            user.access_version += 1
        db.commit()
    assert client.get('/abel/api/auth/me').status_code == 401


def test_create_psychologist_creates_and_links_crp_atomically(auth_http):
    client, engine = auth_http
    with Session(engine) as db:
        db.add(Role(id=2, name='psicologo'))
        db.add(Permission(id=1, key='user.create', resource='user', action='create', sensitivity='PRIVILEGED'))
        db.flush()
        db.add(RolePermission(role_id=1, permission_id=1))
        db.commit()
    assert login(client).status_code == 200
    response = client.post('/abel/api/admin/users', headers={'X-CSRF-Token': client.cookies.get('abel_csrf')}, json={
        'username': 'psico.teste', 'display_name': 'Profissional Teste', 'cpf': '52998224725',
        'phone': '11999999999', 'email': 'teste@example.com', 'address': 'Endereco de teste',
        'role': 'psicologo', 'council_type': 'CRP', 'council_number': '12345', 'council_region': 'SP',
    })
    assert response.status_code == 201, response.text
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'psico.teste'))
        professional = db.get(Professional, user.professional_id)
        assert professional.council_type == 'CRP'
        assert professional.council_number == '12345'
        assert user.workspace_id == 1
        assert user.manager_id == 1
