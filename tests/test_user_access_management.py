from datetime import UTC, date, datetime, timedelta

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes import admin_reports
from backend.app.api.routes.admin_reports import UserUpdate, update_user
from backend.app.db.base import Base
from backend.app.db.models import AuthSession, Role, User, UserRole
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def payload(**changes) -> UserUpdate:
    values = {
        "display_name": "Usuario Teste",
        "cpf": "52998224725",
        "birth_date": date(1990, 1, 1),
        "phone": "11999999999",
        "email": "usuario@example.com",
        "address": "Rua de Teste, 123",
        "role": "atendente",
        "professional_id": None,
        "active": True,
        "expected_version": 1,
    }
    values.update(changes)
    return UserUpdate(**values)


def add_user(db: Session, user_id: int, username: str, role_id: int) -> User:
    user = User(
        id=user_id,
        username=username,
        display_name=username,
        cpf=f"5299822472{user_id}",
        active=True,
        must_reset_password=False,
        access_version=1,
        row_version=1,
    )
    db.add_all([user, UserRole(user_id=user_id, role_id=role_id)])
    return user


def setup_db() -> tuple[Session, User, User]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            Role(id=1, name="gerente", description="Gestor"),
            Role(id=2, name="atendente", description="Recepcao"),
            Role(id=3, name="medico", description="Medico"),
        ]
    )
    actor = add_user(db, 1, "ator", 1)
    target = add_user(db, 2, "alvo", 2)
    db.commit()
    return db, actor, target


def context(user: User) -> AuthContext:
    return AuthContext(
        user=user,
        session=AuthSession(id=10, user_id=user.id, token_hash="x", csrf_hash="y"),
        roles=frozenset({"gerente"}),
    )


def test_access_change_increments_version_and_revokes_sessions(monkeypatch) -> None:
    db, actor, target = setup_db()
    monkeypatch.setattr(admin_reports, "audit", lambda *args, **kwargs: None)
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        AuthSession(
            id=20,
            user_id=target.id,
            token_hash="token",
            csrf_hash="csrf",
            access_version=1,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_seen_at=now,
        )
    )
    db.commit()
    result = update_user(target.id, payload(role="gerente"), context(actor), db)
    assert result["access_version"] == 2
    assert db.get(AuthSession, 20) is None
    db.close()


def test_user_cannot_change_own_access(monkeypatch) -> None:
    db, actor, _ = setup_db()
    monkeypatch.setattr(admin_reports, "audit", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as error:
        update_user(actor.id, payload(role="atendente"), context(actor), db)
    assert error.value.status_code == 409
    db.close()


def test_last_active_manager_is_protected(monkeypatch) -> None:
    db, actor, target = setup_db()
    monkeypatch.setattr(admin_reports, "audit", lambda *args, **kwargs: None)
    db.execute(UserRole.__table__.delete().where(UserRole.user_id == actor.id))
    db.add(UserRole(user_id=actor.id, role_id=2))
    db.execute(UserRole.__table__.delete().where(UserRole.user_id == target.id))
    db.add(UserRole(user_id=target.id, role_id=1))
    db.commit()
    with pytest.raises(HTTPException) as error:
        update_user(target.id, payload(role="atendente"), context(actor), db)
    assert error.value.status_code == 409
    current_role = db.scalar(
        select(Role.name).join(UserRole).where(UserRole.user_id == target.id)
    )
    assert current_role == "gerente"
    db.close()
