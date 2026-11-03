"""add detran operational model

Revision ID: d81a6c9e4301
Revises: c4a0f6b2d901
Create Date: 2026-11-03 11:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d81a6c9e4301"
down_revision: str | Sequence[str] | None = "c4a0f6b2d901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("gender", sa.String(20)))
    op.add_column("patients", sa.Column("marital_status", sa.String(30)))
    op.add_column("patients", sa.Column("process_type", sa.String(80)))
    op.add_column("patients", sa.Column("observations", sa.Text()))
    op.add_column("professionals", sa.Column("phone", sa.String(20)))
    op.add_column("professionals", sa.Column("email", sa.String(254)))
    op.add_column(
        "professionals",
        sa.Column("commission_rate", sa.Numeric(5, 4), server_default="0.6000", nullable=False),
    )
    op.add_column(
        "professionals", sa.Column("row_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_table(
        "service_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "code in ('MEDICAL_EXAM','PSYCHOTECHNICAL')", name="ck_service_types_code_allowed"
        ),
        sa.CheckConstraint("price >= 0", name="ck_service_types_price_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_service_types"),
        sa.UniqueConstraint("code", name="uq_service_types_code"),
    )
    op.create_index("ix_service_types_code", "service_types", ["code"])
    for _name, column in (
        ("service_type_id", sa.Column("service_type_id", sa.Integer())),
        ("scheduled_at", sa.Column("scheduled_at", sa.DateTime())),
        (
            "operational_status",
            sa.Column(
                "operational_status", sa.String(30), server_default="SCHEDULED", nullable=False
            ),
        ),
        (
            "source_kind",
            sa.Column("source_kind", sa.String(20), server_default="LEGACY", nullable=False),
        ),
        ("source_key", sa.Column("source_key", sa.String(120))),
        ("rejection_reason", sa.Column("rejection_reason", sa.String(50))),
        (
            "missing_documents",
            sa.Column("missing_documents", sa.Boolean(), server_default=sa.false(), nullable=False),
        ),
        ("finalized_by_id", sa.Column("finalized_by_id", sa.BigInteger())),
        ("completed_at", sa.Column("completed_at", sa.DateTime())),
    ):
        op.add_column("appointments", column)
    op.create_foreign_key(
        "fk_appointments_service_type_id_service_types",
        "appointments",
        "service_types",
        ["service_type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_appointments_finalized_by_id_users",
        "appointments",
        "users",
        ["finalized_by_id"],
        ["id"],
    )
    op.create_index("ix_appointments_service_type_id", "appointments", ["service_type_id"])
    op.create_index("ix_appointments_scheduled_at", "appointments", ["scheduled_at"])
    op.create_index("ix_appointments_source_key", "appointments", ["source_key"], unique=True)
    op.add_column("payments", sa.Column("commission_rate", sa.Numeric(5, 4)))
    op.add_column("payments", sa.Column("professional_amount", sa.Numeric(12, 2)))
    op.add_column("payments", sa.Column("clinic_amount", sa.Numeric(12, 2)))
    op.create_table(
        "agenda_import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("agenda_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_by_id", sa.BigInteger(), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime()),
        sa.Column("rolled_back_by_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["imported_by_id"], ["users.id"], name="fk_agenda_import_batches_imported_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["rolled_back_by_id"],
            ["users.id"],
            name="fk_agenda_import_batches_rolled_back_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agenda_import_batches"),
        sa.UniqueConstraint("sha256", name="uq_agenda_import_batches_sha256"),
    )
    op.create_index("ix_agenda_import_batches_sha256", "agenda_import_batches", ["sha256"])
    op.create_index(
        "ix_agenda_import_batches_agenda_date", "agenda_import_batches", ["agenda_date"]
    )
    op.create_table(
        "agenda_import_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("patient_id", sa.BigInteger()),
        sa.Column("appointment_id", sa.BigInteger()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["agenda_import_batches.id"],
            ondelete="CASCADE",
            name="fk_agenda_import_rows_batch_id_agenda_import_batches",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name="fk_agenda_import_rows_patient_id_patients"
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointments.id"],
            name="fk_agenda_import_rows_appointment_id_appointments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agenda_import_rows"),
        sa.UniqueConstraint("batch_id", "source_row", name="uq_agenda_import_rows_batch_id"),
        sa.UniqueConstraint("source_key", name="uq_agenda_import_rows_source_key"),
    )
    op.create_index("ix_agenda_import_rows_batch_id", "agenda_import_rows", ["batch_id"])
    op.create_index("ix_agenda_import_rows_source_key", "agenda_import_rows", ["source_key"])


def downgrade() -> None:
    op.drop_table("agenda_import_rows")
    op.drop_table("agenda_import_batches")
    for name in ("clinic_amount", "professional_amount", "commission_rate"):
        op.drop_column("payments", name)
    op.drop_constraint("fk_appointments_finalized_by_id_users", "appointments", type_="foreignkey")
    op.drop_constraint(
        "fk_appointments_service_type_id_service_types", "appointments", type_="foreignkey"
    )
    for index in (
        "ix_appointments_source_key",
        "ix_appointments_scheduled_at",
        "ix_appointments_service_type_id",
    ):
        op.drop_index(index, table_name="appointments")
    for name in (
        "completed_at",
        "finalized_by_id",
        "missing_documents",
        "rejection_reason",
        "source_key",
        "source_kind",
        "operational_status",
        "scheduled_at",
        "service_type_id",
    ):
        op.drop_column("appointments", name)
    op.drop_table("service_types")
    for name in ("row_version", "commission_rate", "email", "phone"):
        op.drop_column("professionals", name)
    for name in ("observations", "process_type", "marital_status", "gender"):
        op.drop_column("patients", name)
