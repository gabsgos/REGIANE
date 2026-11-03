"""store Detran PDF exam metadata on appointments

Revision ID: a7c9e1d2f4b6
Revises: f3b5c7d9e1a2
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1d2f4b6"
down_revision: str | Sequence[str] | None = "f3b5c7d9e1a2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("appointments", sa.Column("process_type", sa.String(length=80), nullable=True))
    op.add_column("appointments", sa.Column("license_category", sa.String(length=10), nullable=True))
    op.add_column("appointments", sa.Column("exam_status", sa.String(length=30), nullable=True))

def downgrade() -> None:
    op.drop_column("appointments", "exam_status")
    op.drop_column("appointments", "license_category")
    op.drop_column("appointments", "process_type")
