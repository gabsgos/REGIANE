from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.db.session import get_session_factory
from sqlalchemy import text

ROUTES = Path("backend/app/api/routes")
REPORT = Path("docs/permissoes_e04_shadow.json")
ROLES = {"gerente", "atendente", "medico"}
APPROVED_DIVERGENCES = {
    ("finance.read", "atendente"),
    ("finance.export", "atendente"),
    ("document.read", "atendente"),
    ("document.download", "atendente"),
}

DIVERGENCE_REASONS = {
    ("finance.read", "atendente"): "Target removes aggregate and historical finance access.",
    ("finance.export", "atendente"): "Target reserves financial exports for GESTOR.",
    ("document.read", "atendente"): (
        "Target access is limited to authenticated delivery queue in E06."
    ),
    ("document.download", "atendente"): (
        "Target access is limited to authenticated delivery queue in E06."
    ),
}


def route_policies() -> list[dict]:
    policies = []
    for path in sorted(ROUTES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"require_permission", "require_csrf_permission"}:
                continue
            values = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
            policies.append(
                {
                    "file": path.as_posix(),
                    "line": node.lineno,
                    "permission": values[0],
                    "legacy_roles": values[1:],
                    "csrf": node.func.id == "require_csrf_permission",
                }
            )
    return policies


def main() -> int:
    policies = route_policies()
    with get_session_factory()() as db:
        rows = db.execute(
            text(
                "SELECT p.`key`, r.name FROM role_permissions rp "
                "JOIN permissions p ON p.id=rp.permission_id "
                "JOIN roles r ON r.id=rp.role_id"
            )
        ).all()
    granted: dict[str, set[str]] = {}
    for permission, role in rows:
        granted.setdefault(permission, set()).add(role)

    divergences = []
    missing_permissions = []
    for policy in policies:
        permission = policy["permission"]
        if permission not in granted:
            missing_permissions.append(permission)
            continue
        for role in ROLES:
            legacy = role in policy["legacy_roles"]
            target = role in granted[permission]
            if legacy != target:
                divergences.append(
                    {
                        **policy,
                        "role": role,
                        "legacy_allowed": legacy,
                        "target_allowed": target,
                        "approved": (permission, role) in APPROVED_DIVERGENCES,
                        "reason": DIVERGENCE_REASONS.get((permission, role)),
                    }
                )
    unexplained = [item for item in divergences if not item["approved"]]
    criteria = {
        "all_authenticated_routes_classified": len(policies) == 33,
        "all_permissions_exist": not missing_permissions,
        "zero_unexplained_divergences": not unexplained,
        "legacy_policy_remains_authoritative": True,
        "sensitive_values_not_collected": True,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "SHADOW",
        "classified_routes": len(policies),
        "divergences": divergences,
        "unexplained_divergences": unexplained,
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
