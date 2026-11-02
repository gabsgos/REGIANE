from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.api.dependencies import AuthContext, _authorization_mode
from backend.app.core.authorization import evaluate_permission
from backend.app.db.models import AuthSession, Permission, Role, RolePermission, User, UserRole
from backend.app.db.session import get_session_factory
from sqlalchemy import select

REPORT = Path("docs/permissoes_e10_runtime.json")
MATRIX = {
    "gerente": {
        "user.read": True,
        "finance.report": True,
        "document.delivery_queue": True,
    },
    "atendente": {
        "finance.read": False,
        "document.delivery_queue": True,
        "document.authenticate": False,
    },
    "medico": {
        "clinical_queue.read": True,
        "document.authenticate": True,
        "finance.read": False,
    },
}


def main() -> int:
    checks: list[dict] = []
    with get_session_factory()() as db:
        for role_name, permissions in MATRIX.items():
            user = db.scalar(
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role_name, User.active.is_(True))
                .order_by(User.id)
            )
            if not user:
                role = db.scalar(select(Role).where(Role.name == role_name))
                for permission, expected in permissions.items():
                    configured = bool(
                        db.scalar(
                            select(RolePermission.permission_id)
                            .join(Permission, Permission.id == RolePermission.permission_id)
                            .where(
                                RolePermission.role_id == role.id,
                                Permission.key == permission,
                            )
                        )
                    )
                    checks.append(
                        {
                            "role": role_name,
                            "permission": permission,
                            "expected": expected,
                            "actual": configured,
                            "decision": "PROFILE_CONFIGURATION_NO_ACTIVE_USER",
                            "pass": configured is expected,
                        }
                    )
                continue
            context = AuthContext(
                user=user,
                session=AuthSession(id=0, user_id=user.id, access_version=user.access_version),
                roles=frozenset({role_name}),
            )
            for permission, expected in permissions.items():
                result = evaluate_permission(
                    db, context, permission, mode="ENFORCE", record=False
                )
                checks.append(
                    {
                        "role": role_name,
                        "permission": permission,
                        "expected": expected,
                        "actual": result.allowed,
                        "decision": result.decision_code,
                        "pass": result.allowed is expected,
                    }
                )
    criteria = {
        "matrix_matches": bool(checks) and all(item.get("pass") for item in checks),
        "all_domains_enforced": all(
            _authorization_mode(permission) == "ENFORCE"
            for permissions in MATRIX.values()
            for permission in permissions
        ),
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
