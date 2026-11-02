from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import token_digest
from backend.app.db.models import AuthSession, Role, User, UserRole
from backend.app.db.session import get_db_session


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    roles: frozenset[str]


PRIVILEGED_PERMISSIONS = frozenset(
    {
        "user.create",
        "user.manage",
        "user.suspend",
        "user.reset_password",
        "access.manage",
        "access.audit",
        "finance.reverse",
        "finance.reconcile",
        "finance.export",
        "backup.restore",
    }
)


def enforce_recent_auth(context: AuthContext, permission_key: str) -> None:
    if permission_key not in PRIVILEGED_PERMISSIONS:
        return
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        minutes=get_settings().step_up_minutes
    )
    if not context.session.created_at or context.session.created_at < cutoff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Autenticacao recente necessaria; entre novamente",
        )


def get_auth_context(
    db: Annotated[Session, Depends(get_db_session)],
    abel_session: Annotated[str | None, Cookie()] = None,
) -> AuthContext:
    if not abel_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nao autenticado")
    now = datetime.now(UTC).replace(tzinfo=None)
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest(abel_session),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if not auth_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida")
    user = db.get(User, auth_session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inativo")
    if auth_session.access_version != user.access_version:
        auth_session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acesso atualizado")
    roles = frozenset(
        db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    auth_session.last_seen_at = now
    db.commit()
    return AuthContext(user=user, session=auth_session, roles=roles)


def require_csrf(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    x_csrf_token: Annotated[str | None, Header()] = None,
    abel_csrf: Annotated[str | None, Cookie()] = None,
) -> AuthContext:
    if (
        not x_csrf_token
        or not abel_csrf
        or x_csrf_token != abel_csrf
        or token_digest(x_csrf_token) != context.session.csrf_hash
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalido")
    return context


def require_roles(*allowed_roles: str):
    def dependency(context: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
        if context.user.must_reset_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Redefinicao de senha obrigatoria",
            )
        if not context.roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        return context

    return dependency


def require_csrf_roles(*allowed_roles: str):
    def dependency(context: Annotated[AuthContext, Depends(require_csrf)]) -> AuthContext:
        if context.user.must_reset_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Redefinicao de senha obrigatoria",
            )
        if not context.roles.intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        return context

    return dependency


def _authorization_mode(permission_key: str) -> str:
    settings = get_settings()
    prefix = permission_key.split(".", 1)[0]
    domain = {
        "user": "admin",
        "access": "admin",
        "finance": "finance",
        "demographic": "clinical",
        "schedule": "clinical",
        "clinical": "clinical",
        "document": "documents",
        "report": "reports",
        "migration_issue": "reports",
    }.get(prefix)
    domain_mode = getattr(settings, f"authorization_{domain}_mode", None) if domain else None
    mode = (domain_mode or settings.authorization_mode).upper()
    if mode not in {"COMPAT", "SHADOW", "ENFORCE"}:
        raise HTTPException(status_code=500, detail="Modo de autorizacao invalido")
    return mode


def require_permission(permission_key: str, *legacy_roles: str):
    def dependency(
        context: Annotated[AuthContext, Depends(get_auth_context)],
        db: Annotated[Session, Depends(get_db_session)],
    ) -> AuthContext:
        if context.user.must_reset_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Redefinicao de senha obrigatoria",
            )
        from backend.app.core.authorization import evaluate_permission

        mode = _authorization_mode(permission_key)
        legacy_allowed = bool(context.roles.intersection(legacy_roles))
        result = evaluate_permission(
            db,
            context,
            permission_key,
            mode=mode,
            legacy_allowed=legacy_allowed,
        )
        allowed = result.allowed if mode == "ENFORCE" else legacy_allowed
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        enforce_recent_auth(context, permission_key)
        return context

    return dependency


def require_csrf_permission(permission_key: str, *legacy_roles: str):
    def dependency(
        context: Annotated[AuthContext, Depends(require_csrf)],
        db: Annotated[Session, Depends(get_db_session)],
    ) -> AuthContext:
        if context.user.must_reset_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Redefinicao de senha obrigatoria",
            )
        from backend.app.core.authorization import evaluate_permission

        mode = _authorization_mode(permission_key)
        legacy_allowed = bool(context.roles.intersection(legacy_roles))
        result = evaluate_permission(
            db,
            context,
            permission_key,
            mode=mode,
            legacy_allowed=legacy_allowed,
        )
        allowed = result.allowed if mode == "ENFORCE" else legacy_allowed
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        enforce_recent_auth(context, permission_key)
        return context

    return dependency
