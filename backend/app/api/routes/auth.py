from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.api.dependencies import AuthContext, get_auth_context, require_csrf
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import LoginRateLimiter
from backend.app.core.security import (
    hash_password,
    needs_rehash,
    new_token,
    token_digest,
    verify_password,
)
from backend.app.db.models import AuditLog, AuthSession, Role, User, UserRole
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/auth", tags=["autenticacao"])
settings = get_settings()
rate_limiter = LoginRateLimiter(settings.login_max_attempts, settings.login_window_seconds)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def audit(db: Session, action: str, user_id: int | None = None) -> None:
    db.add(
        AuditLog(
            occurred_at=datetime.now(UTC).replace(tzinfo=None),
            user_id=user_id,
            action=action,
            entity_type="auth",
            entity_id=str(user_id) if user_id else None,
            before_json=None,
            after_json=None,
            request_id=None,
        )
    )


def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    max_age = settings.session_hours * 3600
    response.set_cookie(
        "abel_session",
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure or settings.environment == "production",
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        "abel_csrf",
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure or settings.environment == "production",
        samesite="strict",
        path="/",
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db_session)],
) -> dict:
    username = payload.username.strip().lower()
    if not username or not payload.password.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas"
        )
    client_host = request.client.host if request.client else "local"
    limiter_key = token_digest(f"{client_host}:{username}")
    if rate_limiter.is_blocked(limiter_key):
        audit(db, "login_rate_limited")
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Tente novamente")
    user = db.scalar(select(User).where(User.username == username, User.active.is_(True)))
    if not user or not verify_password(user.password_hash, payload.password):
        rate_limiter.record_failure(limiter_key)
        audit(db, "login_failed", user.id if user else None)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas"
        )

    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    token = new_token()
    csrf = new_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(token),
        csrf_hash=token_digest(csrf),
        access_version=user.access_version,
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_hours),
        last_seen_at=now,
        revoked_at=None,
    )
    db.add(auth_session)
    audit(db, "login_success", user.id)
    db.commit()
    rate_limiter.reset(limiter_key)
    set_auth_cookies(response, token, csrf)
    roles = list(
        db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    return {
        "user": {"id": user.id, "display_name": user.display_name, "roles": roles},
        "must_reset_password": user.must_reset_password,
        "csrf_token": csrf,
    }


@router.get("/me")
def me(
    response: Response,
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "id": context.user.id,
        "username": context.user.username,
        "display_name": context.user.display_name,
        "roles": sorted(context.roles),
        "workspace_id": context.user.workspace_id,
        "manager_id": context.user.manager_id,
        "must_reset_password": context.user.must_reset_password,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    # Logout is intentionally not CSRF-protected: revoking the current session
    # is safe even when initiated by a cross-site request, while requiring the
    # CSRF token can leave the browser redirected but the server session alive.
    context: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    context.session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    audit(db, "logout", context.user.id)
    db.commit()
    response.delete_cookie("abel_session", path="/")
    response.delete_cookie("abel_csrf", path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    context: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    if not verify_password(context.user.password_hash, payload.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha atual invalida")
    context.user.password_hash = hash_password(payload.new_password)
    context.user.must_reset_password = False
    context.user.access_version += 1
    now = datetime.now(UTC).replace(tzinfo=None)
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == context.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    audit(db, "password_changed", context.user.id)
    db.commit()
    response.delete_cookie("abel_session", path="/")
    response.delete_cookie("abel_csrf", path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
