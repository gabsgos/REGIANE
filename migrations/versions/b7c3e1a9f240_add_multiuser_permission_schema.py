"""add multiuser permission schema

Revision ID: b7c3e1a9f240
Revises: 2e32865e3947
Create Date: 2026-11-02 13:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "b7c3e1a9f240"
down_revision: str | Sequence[str] | None = "2e32865e3947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    ("clinic.read", "clinic", "read", "NORMAL", True),
    ("clinic.manage", "clinic", "manage", "PRIVILEGED", False),
    ("unit.read", "unit", "read", "NORMAL", True),
    ("unit.manage", "unit", "manage", "PRIVILEGED", False),
    ("user.read", "user", "read", "SENSITIVE", True),
    ("user.create", "user", "create", "PRIVILEGED", False),
    ("user.manage", "user", "manage", "PRIVILEGED", False),
    ("user.suspend", "user", "suspend", "PRIVILEGED", False),
    ("user.reset_password", "user", "reset_password", "PRIVILEGED", False),
    ("access.read", "access", "read", "SENSITIVE", True),
    ("access.inspect", "access", "inspect", "SENSITIVE", True),
    ("access.manage", "access", "manage", "PRIVILEGED", False),
    ("access.audit", "access", "audit", "PRIVILEGED", False),
    ("demographic.read", "patient_demographic", "read", "SENSITIVE", True),
    ("demographic.create", "patient_demographic", "create", "SENSITIVE", True),
    ("demographic.write", "patient_demographic", "write", "SENSITIVE", True),
    ("schedule.read", "schedule", "read", "NORMAL", True),
    ("schedule.write", "schedule", "write", "SENSITIVE", True),
    ("schedule.cancel", "schedule", "cancel", "SENSITIVE", True),
    ("schedule.manage_availability", "schedule", "manage_availability", "SENSITIVE", True),
    ("clinical_queue.read", "clinical_worklist", "read", "HIGH_CLINICAL", True),
    ("clinical.read", "clinical_record", "read", "HIGH_CLINICAL", True),
    ("clinical.write", "clinical_record", "write", "HIGH_CLINICAL", True),
    ("clinical.sign", "clinical_record", "sign", "PRIVILEGED", False),
    ("clinical.amend", "clinical_record", "amend", "PRIVILEGED", False),
    ("document.read", "clinical_document", "read", "HIGH_CLINICAL", True),
    ("document.upload", "clinical_document", "upload", "HIGH_CLINICAL", True),
    ("document.download", "clinical_document", "download", "HIGH_CLINICAL", True),
    ("document.authenticate", "clinical_document", "authenticate", "PRIVILEGED", False),
    ("document.delivery_queue", "clinical_document", "delivery_queue", "HIGH_CLINICAL", True),
    ("document.dispatch", "clinical_document", "dispatch", "HIGH_CLINICAL", True),
    ("finance.read", "finance", "read", "SENSITIVE", True),
    ("finance.receive", "finance", "receive", "SENSITIVE", True),
    ("finance.reverse", "finance", "reverse", "PRIVILEGED", False),
    ("finance.reconcile", "finance", "reconcile", "PRIVILEGED", False),
    ("finance.report", "finance", "report", "SENSITIVE", True),
    ("finance.export", "finance", "export", "PRIVILEGED", False),
    ("report.operational", "report", "operational", "SENSITIVE", True),
    ("report.clinical", "report", "clinical", "HIGH_CLINICAL", False),
    ("backup.run", "backup", "run", "PRIVILEGED", False),
    ("backup.restore", "backup", "restore", "PRIVILEGED", False),
    ("migration_issue.read", "migration_issue", "read", "SENSITIVE", True),
)

PROFILE_PERMISSIONS = {
    "gerente": tuple(item[0] for item in PERMISSIONS),
    "atendente": (
        "clinic.read",
        "unit.read",
        "demographic.read",
        "demographic.create",
        "demographic.write",
        "schedule.read",
        "schedule.write",
        "schedule.cancel",
        "finance.receive",
        "document.read",
        "document.download",
        "document.delivery_queue",
        "document.dispatch",
    ),
    "medico": (
        "clinic.read",
        "unit.read",
        "demographic.read",
        "schedule.read",
        "finance.read",
        "clinical_queue.read",
        "document.read",
        "document.upload",
        "document.download",
        "document.authenticate",
    ),
    "psicologo": (
        "clinic.read",
        "unit.read",
        "demographic.read",
        "schedule.read",
        "finance.read",
        "clinical_queue.read",
        "document.read",
        "document.upload",
        "document.download",
    ),
}


def _validate_existing_data() -> None:
    # Offline SQL generation has no connection to inspect existing rows.
    # Runtime upgrade still performs all validations before changing schema.
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    duplicate_cpf = bind.execute(
        sa.text(
            "SELECT cpf FROM users WHERE cpf IS NOT NULL AND cpf <> '' "
            "GROUP BY cpf HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_cpf:
        raise RuntimeError("Usuarios possuem CPF duplicado; normalize antes da migration")
    multiple_roles = bind.execute(
        sa.text(
            "SELECT user_id FROM user_roles GROUP BY user_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if multiple_roles:
        raise RuntimeError("Usuario possui mais de um perfil; normalize antes da migration")
    invalid_council = bind.execute(
        sa.text(
            "SELECT id FROM professionals "
            "WHERE council_type NOT IN ('CRM','CRP') LIMIT 1"
        )
    ).first()
    if invalid_council:
        raise RuntimeError("Profissional possui conselho diferente de CRM ou CRP")


def _seed_access_catalog() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("key", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("sensitivity", sa.String()),
        sa.column("delegable", sa.Boolean()),
        sa.column("active", sa.Boolean()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer()),
        sa.column("permission_id", sa.Integer()),
    )

    role_descriptions = {
        "gerente": "Gestor",
        "atendente": "Recepcao",
        "medico": "Profissional clinico CRM ou CRP",
        "psicologo": "Profissional clinico CRP",
    }
    for role_name, description in role_descriptions.items():
        role_id = bind.execute(sa.select(roles.c.id).where(roles.c.name == role_name)).scalar()
        if role_id is None:
            bind.execute(roles.insert().values(name=role_name, description=description))

    for key, resource, action, sensitivity, delegable in PERMISSIONS:
        permission_id = bind.execute(
            sa.select(permissions.c.id).where(permissions.c.key == key)
        ).scalar()
        if permission_id is None:
            bind.execute(
                permissions.insert().values(
                    key=key,
                    resource=resource,
                    action=action,
                    sensitivity=sensitivity,
                    delegable=delegable,
                    active=True,
                )
            )

    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    permission_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    existing = set(
        bind.execute(
            sa.select(role_permissions.c.role_id, role_permissions.c.permission_id)
        ).all()
    )
    rows = [
        {"role_id": role_ids[role_name], "permission_id": permission_ids[permission_key]}
        for role_name, permission_keys in PROFILE_PERMISSIONS.items()
        for permission_key in permission_keys
        if (role_ids[role_name], permission_ids[permission_key]) not in existing
    ]
    if rows:
        bind.execute(role_permissions.insert(), rows)


def upgrade() -> None:
    _validate_existing_data()
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("address", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("access_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index("ix_users_cpf", "users", ["cpf"], unique=True)

    op.add_column(
        "roles", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "roles", sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False)
    )
    op.add_column(
        "roles", sa.Column("system_defined", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.create_unique_constraint("uq_user_roles_user_id", "user_roles", ["user_id"])
    op.create_check_constraint(
        "ck_professionals_council_type_allowed",
        "professionals",
        "council_type in ('CRM','CRP')",
    )
    op.add_column(
        "auth_sessions",
        sa.Column("access_version", sa.Integer(), server_default="1", nullable=False),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("resource", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("sensitivity", sa.String(length=30), nullable=False),
        sa.Column("delegable", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("resource", "action", name="uq_permissions_resource"),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)
    op.create_index("ix_permissions_resource", "permissions", ["resource"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )
    op.create_table(
        "user_permission_overrides",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("effect", sa.String(length=5), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=True),
        sa.Column("scope_id", sa.String(length=80), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "effect in ('ALLOW','DENY')",
            name="ck_user_permission_overrides_effect_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_user_permission_overrides_created_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_user_permission_overrides_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_permission_overrides_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_permission_overrides"),
    )
    op.create_index(
        "ix_user_permission_override_lookup",
        "user_permission_overrides",
        ["user_id", "permission_id", "expires_at"],
        unique=False,
    )
    op.create_table(
        "access_grants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=True),
        sa.Column("scope_id", sa.String(length=80), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("requested_by_id", sa.BigInteger(), nullable=False),
        sa.Column("approved_by_id", sa.BigInteger(), nullable=True),
        sa.Column("revoked_by_id", sa.BigInteger(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status in ('PENDING','ACTIVE','REVOKED','EXPIRED')",
            name="ck_access_grants_status_allowed",
        ),
        sa.CheckConstraint("expires_at > starts_at", name="ck_access_grants_valid_period"),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name="fk_access_grants_approved_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_access_grants_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["users.id"], name="fk_access_grants_requested_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"], ["users.id"], name="fk_access_grants_revoked_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_access_grants_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_access_grants"),
    )
    op.create_index(
        "ix_access_grant_lookup",
        "access_grants",
        ["user_id", "permission_id", "status", "expires_at"],
        unique=False,
    )
    op.create_table(
        "authorization_decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("permission_key", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("decision_code", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=True),
        sa.Column("scope_hash", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_authorization_decisions_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_authorization_decisions"),
    )
    op.create_index(
        "ix_authorization_decision_actor_time",
        "authorization_decisions",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_decision_correlation",
        "authorization_decisions",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "ix_authorization_decisions_permission_key",
        "authorization_decisions",
        ["permission_key"],
        unique=False,
    )
    _seed_access_catalog()


def downgrade() -> None:
    op.drop_table("authorization_decisions")
    op.drop_table("access_grants")
    op.drop_table("user_permission_overrides")
    op.drop_table("role_permissions")
    op.drop_table("permissions")

    op.drop_column("auth_sessions", "access_version")
    op.drop_constraint("ck_professionals_council_type_allowed", "professionals", type_="check")
    op.drop_constraint("uq_user_roles_user_id", "user_roles", type_="unique")
    op.drop_column("roles", "system_defined")
    op.drop_column("roles", "status")
    op.drop_column("roles", "version")
    op.drop_index("ix_users_cpf", table_name="users")
    op.drop_column("users", "access_version")
    op.drop_column("users", "address")
    op.drop_column("users", "email")
    op.drop_column("users", "birth_date")
