from __future__ import annotations

import json
import secrets
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.core.security import hash_password
from backend.app.db.models import AuditLog, Professional, Role, User, UserRole
from backend.app.db.session import get_session_factory
from sqlalchemy import select

SECRET_FILE = Path("data/homologation-doctor.secret")


def main() -> int:
    payload = json.load(sys.stdin)
    username = payload["username"].strip().lower()
    temporary_password = secrets.token_urlsafe(18)
    with get_session_factory()() as db, db.begin():
        role = db.scalar(select(Role).where(Role.name == "medico"))
        if not role:
            raise RuntimeError("Perfil medico nao encontrado")
        professional = db.scalar(
            select(Professional).where(
                Professional.council_type == "CRM",
                Professional.council_number == payload["council_number"],
            )
        )
        if not professional:
            professional = Professional(
                name=payload["display_name"].strip(),
                council_type="CRM",
                council_number=payload["council_number"].strip(),
                council_region="SP",
                cpf=payload["cpf"],
                specialty="Homologacao",
                active=True,
            )
            db.add(professional)
            db.flush()
        user = db.scalar(
            select(User).where((User.username == username) | (User.cpf == payload["cpf"]))
        )
        if user and user.username != username:
            raise RuntimeError("CPF ja associado a outro usuario")
        if not user:
            user = User(
                username=username,
                display_name=payload["display_name"].strip(),
                password_hash=hash_password(temporary_password),
                cpf=payload["cpf"],
                birth_date=date.fromisoformat(payload["birth_date"]),
                phone=payload["phone"].strip(),
                email=payload["email"].strip().lower(),
                address=payload["address"].strip(),
                professional_id=professional.id,
                active=True,
                must_reset_password=True,
            )
            db.add(user)
            db.flush()
        else:
            user.display_name = payload["display_name"].strip()
            user.password_hash = hash_password(temporary_password)
            user.birth_date = date.fromisoformat(payload["birth_date"])
            user.phone = payload["phone"].strip()
            user.email = payload["email"].strip().lower()
            user.address = payload["address"].strip()
            user.professional_id = professional.id
            user.active = True
            user.must_reset_password = True
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.add(
            AuditLog(
                occurred_at=datetime.now(UTC).replace(tzinfo=None),
                user_id=None,
                action="homologation_user_create",
                entity_type="users",
                entity_id=str(user.id),
                before_json=None,
                after_json={
                    "username": username,
                    "role": "medico",
                    "professional_id": professional.id,
                    "council": "CRM-SP ***" + payload["council_number"][-3:],
                    "cpf": "***" + payload["cpf"][-3:],
                    "must_reset_password": True,
                },
                request_id="user-authorized-homologation-2026-11-02",
            )
        )
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_text(
        f"username={username}\npassword={temporary_password}\nchange_required=true\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "username": username,
                "role": "medico",
                "professional_active": True,
                "must_reset_password": True,
                "credential_file": str(SECRET_FILE),
                "integrity": "PASS",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
