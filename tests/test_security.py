from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.app.api import dependencies
from backend.app.api.dependencies import (
    AuthContext,
    enforce_recent_auth,
    require_csrf,
    require_roles,
)
from backend.app.core.rate_limit import LoginRateLimiter
from backend.app.core.security import hash_password, token_digest, verify_password
from backend.app.db.models import AuthSession, User
from fastapi import HTTPException
from tools.validate_auth import read_secret


def test_argon2_and_token_digest() -> None:
    password_hash = hash_password("senha-forte-de-teste")
    assert password_hash.startswith("$argon2")
    assert verify_password(password_hash, "senha-forte-de-teste") is True
    assert verify_password(password_hash, "incorreta") is False
    assert token_digest("abc") != token_digest("abcd")


def test_rate_limiter_blocks_and_resets() -> None:
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("key")
    assert limiter.is_blocked("key") is False
    limiter.record_failure("key")
    assert limiter.is_blocked("key") is True
    limiter.reset("key")
    assert limiter.is_blocked("key") is False


def test_rbac_rejects_missing_role() -> None:
    context = AuthContext(
        user=User(id=1, username="u", display_name="U", active=True, must_reset_password=False),
        session=AuthSession(
            id=1,
            user_id=1,
            token_hash="x" * 64,
            csrf_hash="y" * 64,
            created_at=None,
            expires_at=None,
            last_seen_at=None,
        ),
        roles=frozenset({"atendente"}),
    )
    dependency = require_roles("gerente")
    try:
        dependency(context)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("RBAC deveria rejeitar o perfil")


def test_rbac_accepts_required_role() -> None:
    context = AuthContext(
        user=User(id=1, username="u", display_name="U", active=True, must_reset_password=False),
        session=AuthSession(
            id=1,
            user_id=1,
            token_hash="x" * 64,
            csrf_hash="y" * 64,
            created_at=None,
            expires_at=None,
            last_seen_at=None,
        ),
        roles=frozenset({"gerente"}),
    )
    assert require_roles("gerente")(context) is context


def test_auth_validator_prefers_valid_production_secret(tmp_path: Path) -> None:
    production = tmp_path / "production.secret"
    initial = tmp_path / "initial.secret"
    production.write_text(
        "username=abel-admin\npassword=producao\nchange_required=false\n",
        encoding="utf-8",
    )
    initial.write_text("ROTATED\n", encoding="utf-8")

    assert read_secret((production, initial)) == {
        "username": "abel-admin",
        "password": "producao",
        "change_required": "false",
    }


def test_authorization_mode_is_selected_per_domain(monkeypatch) -> None:
    settings = SimpleNamespace(
        authorization_mode="COMPAT",
        authorization_admin_mode="ENFORCE",
        authorization_finance_mode="SHADOW",
        authorization_clinical_mode=None,
        authorization_documents_mode=None,
        authorization_reports_mode=None,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    assert dependencies._authorization_mode("user.manage") == "ENFORCE"
    assert dependencies._authorization_mode("finance.report") == "SHADOW"
    assert dependencies._authorization_mode("clinical.read") == "COMPAT"


def test_privileged_action_requires_recent_auth(monkeypatch) -> None:
    settings = SimpleNamespace(step_up_minutes=15)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    context = AuthContext(
        user=User(id=1, username="u", display_name="U", active=True),
        session=AuthSession(
            id=1,
            user_id=1,
            token_hash="x" * 64,
            csrf_hash="y" * 64,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=16),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            last_seen_at=datetime.now(UTC).replace(tzinfo=None),
        ),
        roles=frozenset({"gerente"}),
    )
    with pytest.raises(HTTPException, match="Autenticacao recente"):
        enforce_recent_auth(context, "finance.reverse")
    enforce_recent_auth(context, "finance.read")


def test_csrf_rejects_mismatch() -> None:
    context = AuthContext(
        user=User(id=1, username="u", display_name="U", active=True),
        session=AuthSession(id=1, user_id=1, csrf_hash=token_digest("correto")),
        roles=frozenset({"gerente"}),
    )
    with pytest.raises(HTTPException, match="CSRF invalido"):
        require_csrf(context, "incorreto", "incorreto")
    assert require_csrf(context, "correto", "correto") is context
