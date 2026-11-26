"""Atomic and idempotent patient intake requests."""

import sqlalchemy as sa
from alembic import op

revision = "b5c8e4a7d901"
down_revision = "a4e75c1d902b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operation_intakes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger(), nullable=True, server_default="1"),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "idempotency_key"),
    )
    op.create_index("ix_operation_intakes_workspace_id", "operation_intakes", ["workspace_id"])
    op.create_index(
        "ix_operation_intakes_idempotency_key", "operation_intakes", ["idempotency_key"]
    )
    op.create_index("ix_operation_intakes_patient_id", "operation_intakes", ["patient_id"])


def downgrade():
    op.drop_table("operation_intakes")
