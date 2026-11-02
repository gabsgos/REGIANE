from datetime import UTC, datetime, timedelta

from backend.app.api.dependencies import AuthContext
from backend.app.core.authorization import evaluate_permission
from backend.app.db.base import Base
from backend.app.db.models import (
    AccessGrant,
    AuthSession,
    Permission,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
    UserRole,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def authorization_context(db: Session) -> AuthContext:
    user = User(
        id=1,
        username="gestor",
        display_name="Gestor",
        active=True,
        must_reset_password=False,
    )
    role = Role(id=1, name="gerente", description="Gestor")
    permission = Permission(
        id=1,
        key="user.read",
        resource="user",
        action="read",
        sensitivity="SENSITIVE",
        delegable=True,
        active=True,
    )
    db.add_all(
        [
            user,
            role,
            permission,
            UserRole(user_id=1, role_id=1),
            RolePermission(role_id=1, permission_id=1),
        ]
    )
    db.commit()
    return AuthContext(
        user=user,
        session=AuthSession(id=1, user_id=1, token_hash="x", csrf_hash="y"),
        roles=frozenset({"gerente"}),
    )


def test_profile_permission_allows_and_unknown_permission_denies() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        allowed = evaluate_permission(db, context, "user.read", record=False)
        denied = evaluate_permission(db, context, "unknown", record=False)
    assert allowed.allowed is True
    assert allowed.decision_code == "PROFILE_ALLOW"
    assert denied.allowed is False
    assert denied.decision_code == "PERMISSION_NOT_FOUND"


def test_explicit_deny_precedes_profile_permission() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        db.add(
            UserPermissionOverride(
                id=1,
                user_id=1,
                permission_id=1,
                effect="DENY",
                scope_type="CLINIC",
                scope_id=None,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
                reason="Teste de precedencia",
                created_by_id=1,
            )
        )
        db.commit()
        result = evaluate_permission(db, context, "user.read", record=False)
    assert result.allowed is False
    assert result.decision_code == "EXPLICIT_DENY"


def test_explicit_allow_precedes_missing_profile_permission() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        db.query(RolePermission).delete()
        db.add(
            UserPermissionOverride(
                id=1,
                user_id=1,
                permission_id=1,
                effect="ALLOW",
                scope_type="CLINIC",
                scope_id=None,
                expires_at=None,
                reason="Teste de permissao explicita",
                created_by_id=1,
            )
        )
        db.commit()
        result = evaluate_permission(db, context, "user.read", record=False)
    assert result.allowed is True
    assert result.decision_code == "EXPLICIT_ALLOW"


def test_active_temporary_grant_allows_without_profile_permission() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        db.query(RolePermission).delete()
        now = datetime.now(UTC).replace(tzinfo=None)
        db.add(
            AccessGrant(
                id=1,
                user_id=1,
                permission_id=1,
                scope_type="CLINIC",
                scope_id=None,
                starts_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=30),
                status="ACTIVE",
                reason="Teste de grant temporario",
                requested_by_id=1,
                approved_by_id=1,
            )
        )
        db.commit()
        result = evaluate_permission(db, context, "user.read", record=False)
    assert result.allowed is True
    assert result.decision_code == "TEMPORARY_GRANT"


def test_expired_temporary_grant_is_denied() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        db.query(RolePermission).delete()
        now = datetime.now(UTC).replace(tzinfo=None)
        db.add(
            AccessGrant(
                id=1,
                user_id=1,
                permission_id=1,
                scope_type="CLINIC",
                starts_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
                status="ACTIVE",
                reason="Grant expirado",
                requested_by_id=1,
                approved_by_id=1,
            )
        )
        db.commit()
        result = evaluate_permission(db, context, "user.read", record=False)
    assert result.allowed is False
    assert result.decision_code == "NOT_GRANTED"


def test_assigned_scope_fails_closed_without_resource() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        result = evaluate_permission(
            db,
            context,
            "user.read",
            scope_type="ASSIGNED",
            scope_id=None,
            record=False,
        )
    assert result.allowed is False
    assert result.decision_code == "INVALID_SCOPE"


def test_resolved_scope_can_fail_closed() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        context = authorization_context(db)
        result = evaluate_permission(
            db,
            context,
            "user.read",
            scope_type="RESOURCE",
            scope_id="42",
            scope_valid=False,
            record=False,
        )
    assert result.allowed is False
    assert result.decision_code == "SCOPE_NOT_ALLOWED"
