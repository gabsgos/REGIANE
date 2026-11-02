"""add clinical delivery workflow

Revision ID: c4a0f6b2d901
Revises: b7c3e1a9f240
Create Date: 2026-11-02 17:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a0f6b2d901"
down_revision: str | Sequence[str] | None = "b7c3e1a9f240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "workflow_status",
            sa.String(length=40),
            server_default="PAGAMENTO_PENDENTE",
            nullable=False,
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("reanalysis_required", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("appointments", sa.Column("operational_observation", sa.Text(), nullable=True))
    op.create_index(
        "ix_appointments_workflow_status", "appointments", ["workflow_status"], unique=False
    )
    op.add_column(
        "clinical_documents",
        sa.Column(
            "workflow_status",
            sa.String(length=30),
            server_default="PDF_AUTENTICADO",
            nullable=False,
        ),
    )
    op.add_column(
        "clinical_documents", sa.Column("authenticated_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "clinical_documents",
        sa.Column("authenticated_by_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_clinical_documents_authenticated_by_id_users",
        "clinical_documents",
        "users",
        ["authenticated_by_id"],
        ["id"],
    )
    op.create_table(
        "document_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("appointment_id", sa.BigInteger(), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=False),
        sa.Column("delivered_by_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("destination_masked", sa.String(length=120), nullable=False),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "channel in ('telefone','whatsapp_manual','email_manual','presencial')",
            name="ck_document_deliveries_channel_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], name="fk_document_deliveries_appointment_id"
        ),
        sa.ForeignKeyConstraint(
            ["delivered_by_id"], ["users.id"], name="fk_document_deliveries_delivered_by_id"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["clinical_documents.id"], name="fk_document_deliveries_document_id"
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name="fk_document_deliveries_patient_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_deliveries"),
    )
    op.create_index(
        "ix_document_deliveries_appointment_id",
        "document_deliveries",
        ["appointment_id"],
        unique=False,
    )
    op.execute("UPDATE appointments SET workflow_status='CANCELADO' WHERE status='cancelado'")
    op.execute(
        "UPDATE appointments a SET workflow_status='LIBERADO_PARA_MEDICO' "
        "WHERE status='aberto' AND (doctor_id IS NOT NULL OR psychologist_id IS NOT NULL) "
        "AND EXISTS (SELECT 1 FROM payments p WHERE p.appointment_id=a.id AND p.status='pago')"
    )
    op.execute(
        "UPDATE clinical_documents SET authenticated_at=created_at, "
        "authenticated_by_id=uploaded_by_id"
    )


def downgrade() -> None:
    op.drop_table("document_deliveries")
    op.drop_constraint(
        "fk_clinical_documents_authenticated_by_id_users",
        "clinical_documents",
        type_="foreignkey",
    )
    op.drop_column("clinical_documents", "authenticated_by_id")
    op.drop_column("clinical_documents", "authenticated_at")
    op.drop_column("clinical_documents", "workflow_status")
    op.drop_index("ix_appointments_workflow_status", table_name="appointments")
    op.drop_column("appointments", "operational_observation")
    op.drop_column("appointments", "reanalysis_required")
    op.drop_column("appointments", "workflow_status")
