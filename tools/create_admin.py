from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password
from backend.app.db.models import Role, User, UserRole
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria ou redefine o administrador local")
    parser.add_argument("--username", default="abel-admin")
    parser.add_argument("--secret-file", type=Path, default=Path("data/initial-admin.secret"))
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    password = secrets.token_urlsafe(18)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as session, session.begin():
        role = session.scalar(select(Role).where(Role.name == "gerente"))
        if not role:
            role = Role(name="gerente", description="Administracao e financeiro")
            session.add(role)
            session.flush()
        user = session.scalar(select(User).where(User.username == args.username))
        if not user:
            user = User(
                username=args.username,
                display_name="Administrador ABEL",
                password_hash=hash_password(password),
                active=True,
                must_reset_password=True,
            )
            session.add(user)
            session.flush()
        else:
            user.password_hash = hash_password(password)
            user.active = True
            user.must_reset_password = True
        if not session.get(UserRole, (user.id, role.id)):
            session.add(UserRole(user_id=user.id, role_id=role.id))
    args.secret_file.parent.mkdir(parents=True, exist_ok=True)
    args.secret_file.write_text(
        f"username={args.username}\npassword={password}\nchange_required=true\n", encoding="utf-8"
    )
    print(f"Administrador preparado; credencial inicial salva em {args.secret_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
