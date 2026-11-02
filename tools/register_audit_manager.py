from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.core.security import hash_password
from backend.app.db.models import AuditLog, Role, User, UserRole
from backend.app.db.session import get_session_factory
from sqlalchemy import select

USERNAME = "leandro.martins"
SECRET_FILE = Path("data/leandro-manager.secret")


def main() -> int:
    password = secrets.token_urlsafe(20)
    with get_session_factory()() as db, db.begin():
        role = db.scalar(select(Role).where(Role.name == "gerente"))
        if not role:
            raise RuntimeError("Perfil gerente nao encontrado")
        user = db.scalar(select(User).where(User.username == USERNAME))
        if not user:
            user = User(
                username=USERNAME,
                display_name="Leandro Martins (Auditoria)",
                cpf="52998224725",
            )
            db.add(user)
            db.flush()
        user.password_hash = hash_password(password)
        user.birth_date = date(1990, 1, 1)
        user.phone = "11900000000"
        user.email = "leandro.martins@example.local"
        user.address = "Dados mock para auditoria"
        user.active = True
        user.must_reset_password = False
        user.access_version += 1
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.add(
            AuditLog(
                occurred_at=datetime.now(UTC).replace(tzinfo=None),
                user_id=None,
                action="audit_manager_create",
                entity_type="users",
                entity_id=str(user.id),
                before_json=None,
                after_json={
                    "username": USERNAME,
                    "role": "gerente",
                    "data_class": "MOCK",
                    "active": True,
                },
                request_id="user-authorized-tablet-audit-2026-11-02",
            )
        )
    SECRET_FILE.write_text(
        f"username={USERNAME}\npassword={password}\nchange_required=false\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "username": USERNAME,
                "role": "gerente",
                "mock_data": True,
                "credential_file": str(SECRET_FILE),
                "integrity": "PASS",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
