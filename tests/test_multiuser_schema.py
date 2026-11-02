import importlib.util
from pathlib import Path

from backend.app.db.models import (
    AccessGrant,
    Appointment,
    AuthorizationDecision,
    AuthSession,
    ClinicalDocument,
    DocumentDelivery,
    Permission,
    RolePermission,
    User,
    UserPermissionOverride,
    UserRole,
)
from sqlalchemy import UniqueConstraint


def load_migration_module():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "b7c3e1a9f240_add_multiuser_permission_schema.py"
    )
    spec = importlib.util.spec_from_file_location("multiuser_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multiuser_tables_and_access_version_are_in_metadata() -> None:
    assert {
        Permission.__tablename__,
        RolePermission.__tablename__,
        UserPermissionOverride.__tablename__,
        AccessGrant.__tablename__,
        AuthorizationDecision.__tablename__,
    } == {
        "permissions",
        "role_permissions",
        "user_permission_overrides",
        "access_grants",
        "authorization_decisions",
    }
    assert "access_version" in User.__table__.c
    assert "access_version" in AuthSession.__table__.c
    assert {"birth_date", "email", "address"}.issubset(User.__table__.c.keys())


def test_user_has_exactly_one_role_constraint() -> None:
    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in UserRole.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("user_id",) in unique_columns


def test_seed_has_three_profiles_and_42_unique_permissions() -> None:
    migration = load_migration_module()
    keys = [item[0] for item in migration.PERMISSIONS]
    assert len(keys) == len(set(keys)) == 42
    assert set(migration.PROFILE_PERMISSIONS) == {"gerente", "atendente", "medico"}
    assert "user.create" in migration.PROFILE_PERMISSIONS["gerente"]
    assert "user.create" not in migration.PROFILE_PERMISSIONS["atendente"]
    assert "finance.reverse" not in migration.PROFILE_PERMISSIONS["atendente"]
    assert "document.authenticate" in migration.PROFILE_PERMISSIONS["medico"]


def test_clinical_delivery_workflow_is_in_metadata() -> None:
    assert {"workflow_status", "reanalysis_required", "operational_observation"}.issubset(
        Appointment.__table__.c.keys()
    )
    assert {"workflow_status", "authenticated_at", "authenticated_by_id"}.issubset(
        ClinicalDocument.__table__.c.keys()
    )
    assert DocumentDelivery.__tablename__ == "document_deliveries"
