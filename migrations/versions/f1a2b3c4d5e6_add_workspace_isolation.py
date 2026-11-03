"""Add single-workspace membership and tenant columns.

Legacy rows are assigned to workspace 1 (ABEL legacy) so the migration is
backward-compatible. Application authorization must make the columns
mandatory for new writes before a future NOT NULL migration.
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d81a6c9e4301"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "patients",
    "professionals",
    "appointments",
    "payments",
    "financial_movements",
    "clinical_documents",
    "agenda_import_batches",
    "agenda_import_rows",
)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index("ix_workspace_members_manager", "workspace_members", ["manager_id"])

    op.execute(
        sa.text(
            "INSERT INTO workspaces (id, name, slug, status) "
            "VALUES (1, 'ABEL legado', 'abel-legado', 'ACTIVE')"
        )
    )
    op.add_column("users", sa.Column("workspace_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("manager_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])
    op.create_index("ix_users_manager_id", "users", ["manager_id"])
    op.create_foreign_key("fk_users_workspace", "users", "workspaces", ["workspace_id"], ["id"])
    op.create_foreign_key("fk_users_manager", "users", "users", ["manager_id"], ["id"])
    op.execute(sa.text("UPDATE users SET workspace_id = 1 WHERE workspace_id IS NULL"))

    for table in TENANT_TABLES:
        op.add_column(
            table,
            sa.Column("workspace_id", sa.BigInteger(), nullable=True, server_default="1"),
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
        op.create_foreign_key(
            f"fk_{table}_workspace", table, "workspaces", ["workspace_id"], ["id"]
        )
        op.execute(sa.text(f"UPDATE {table} SET workspace_id = 1 WHERE workspace_id IS NULL"))


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_constraint(f"fk_{table}_workspace", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_constraint("fk_users_manager", "users", type_="foreignkey")
    op.drop_constraint("fk_users_workspace", "users", type_="foreignkey")
    op.drop_index("ix_users_manager_id", table_name="users")
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_column("users", "manager_id")
    op.drop_column("users", "workspace_id")
    op.drop_index("ix_workspace_members_manager", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
