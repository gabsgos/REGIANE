from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AccessGrant,
    AuthorizationDecision,
    Permission,
    RolePermission,
    UserPermissionOverride,
    UserRole,
)

if TYPE_CHECKING:
    from backend.app.api.dependencies import AuthContext

AuthorizationMode = Literal["COMPAT", "SHADOW", "ENFORCE"]
VALID_SCOPES = frozenset({"SELF", "CLINIC", "ASSIGNED", "PROFESSIONAL", "RESOURCE", "UNIT"})


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    decision_code: str
    sources: tuple[str, ...] = ()


def _scope_filter(model, scope_type: str, scope_id: str | None):
    return (
        or_(model.scope_type.is_(None), model.scope_type == scope_type),
        or_(model.scope_id.is_(None), model.scope_id == scope_id),
    )


def evaluate_permission(
    db: Session,
    context: AuthContext,
    permission_key: str,
    *,
    scope_type: str = "CLINIC",
    scope_id: str | None = None,
    scope_valid: bool = True,
    correlation_id: str | None = None,
    mode: AuthorizationMode = "COMPAT",
    legacy_allowed: bool | None = None,
    record: bool = True,
) -> AuthorizationResult:
    now = datetime.now(UTC).replace(tzinfo=None)
    permission = db.scalar(
        select(Permission).where(Permission.key == permission_key, Permission.active.is_(True))
    )
    if scope_type not in VALID_SCOPES or (scope_type in {"ASSIGNED", "RESOURCE"} and not scope_id):
        result = AuthorizationResult(False, "INVALID_SCOPE")
    elif not scope_valid:
        result = AuthorizationResult(False, "SCOPE_NOT_ALLOWED")
    elif not permission:
        result = AuthorizationResult(False, "PERMISSION_NOT_FOUND")
    else:
        override = db.scalar(
            select(UserPermissionOverride)
            .where(
                UserPermissionOverride.user_id == context.user.id,
                UserPermissionOverride.permission_id == permission.id,
                or_(
                    UserPermissionOverride.expires_at.is_(None),
                    UserPermissionOverride.expires_at > now,
                ),
                *_scope_filter(UserPermissionOverride, scope_type, scope_id),
            )
            .order_by(UserPermissionOverride.id.desc())
        )
        if override and override.effect == "DENY":
            result = AuthorizationResult(False, "EXPLICIT_DENY", (f"override:{override.id}",))
        elif override and override.effect == "ALLOW":
            result = AuthorizationResult(True, "EXPLICIT_ALLOW", (f"override:{override.id}",))
        else:
            grant = db.scalar(
                select(AccessGrant)
                .where(
                    AccessGrant.user_id == context.user.id,
                    AccessGrant.permission_id == permission.id,
                    AccessGrant.status == "ACTIVE",
                    AccessGrant.starts_at <= now,
                    AccessGrant.expires_at > now,
                    *_scope_filter(AccessGrant, scope_type, scope_id),
                )
                .order_by(AccessGrant.expires_at.desc())
            )
            profile_permission = db.scalar(
                select(RolePermission.permission_id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == context.user.id,
                    RolePermission.permission_id == permission.id,
                )
            )
            if grant:
                result = AuthorizationResult(True, "TEMPORARY_GRANT", (f"grant:{grant.id}",))
            elif profile_permission:
                result = AuthorizationResult(True, "PROFILE_ALLOW", tuple(sorted(context.roles)))
            else:
                result = AuthorizationResult(False, "NOT_GRANTED")

    if record:
        scope_hash = hashlib.sha256(scope_id.encode()).hexdigest() if scope_id else None
        db.add(
            AuthorizationDecision(
                occurred_at=now,
                user_id=context.user.id,
                permission_key=permission_key,
                resource_type=scope_type,
                resource_id=None,
                allowed=result.allowed,
                decision_code=result.decision_code,
                scope_type=scope_type,
                scope_hash=scope_hash,
                correlation_id=correlation_id,
                sources_json={
                    "sources": list(result.sources),
                    "mode": mode,
                    "legacy_allowed": legacy_allowed,
                    "divergent": legacy_allowed is not None and legacy_allowed != result.allowed,
                },
            )
        )
        db.commit()
    return result
