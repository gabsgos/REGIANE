from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class UserRoleName(StrEnum):
    MANAGER = "gerente"
    ATTENDANT = "atendente"
    DOCTOR = "medico"
    PSYCHOLOGIST = "psicologo"


class AppointmentStatus(StrEnum):
    OPEN = "aberto"
    COMPLETED = "concluido"
    CANCELLED = "cancelado"


class PaymentStatus(StrEnum):
    PENDING = "pendente"
    PAID = "pago"
    REVERSED = "estornado"


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    address_json: Mapped[dict | None] = mapped_column(JSON)
    gender: Mapped[str | None] = mapped_column(String(20))
    marital_status: Mapped[str | None] = mapped_column(String(30))
    process_type: Mapped[str | None] = mapped_column(String(80))
    observations: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    __mapper_args__ = {"version_id_col": row_version}


class Professional(TimestampMixin, Base):
    __tablename__ = "professionals"
    __table_args__ = (
        UniqueConstraint("council_type", "council_number"),
        CheckConstraint("council_type in ('CRM','CRP')", name="council_type_allowed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    council_type: Mapped[str] = mapped_column(String(10))
    council_number: Mapped[str] = mapped_column(String(20))
    council_region: Mapped[str | None] = mapped_column(String(5))
    cpf: Mapped[str | None] = mapped_column(String(11))
    specialty: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.6000"), server_default="0.6000", nullable=False
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __mapper_args__ = {"version_id_col": row_version}


class ServiceType(TimestampMixin, Base):
    __tablename__ = "service_types"
    __table_args__ = (
        CheckConstraint("code in ('MEDICAL_EXAM','PSYCHOTECHNICAL')", name="code_allowed"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(Text)
    professional_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_reset_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    __mapper_args__ = {"version_id_col": row_version}


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkspaceInvite(TimestampMixin, Base):
    __tablename__ = "workspace_invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", server_default="PENDING")
    reason: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE")
    system_defined: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("resource", "action"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    resource: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80))
    sensitivity: Mapped[str] = mapped_column(String(30))
    delegable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserPermissionOverride(TimestampMixin, Base):
    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        CheckConstraint("effect in ('ALLOW','DENY')", name="effect_allowed"),
        Index(
            "ix_user_permission_override_lookup",
            "user_id",
            "permission_id",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))
    effect: Mapped[str] = mapped_column(String(5))
    scope_type: Mapped[str | None] = mapped_column(String(40))
    scope_id: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(255))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class AccessGrant(TimestampMixin, Base):
    __tablename__ = "access_grants"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING','ACTIVE','REVOKED','EXPIRED')", name="status_allowed"
        ),
        CheckConstraint("expires_at > starts_at", name="valid_period"),
        Index("ix_access_grant_lookup", "user_id", "permission_id", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))
    scope_type: Mapped[str | None] = mapped_column(String(40))
    scope_id: Mapped[str | None] = mapped_column(String(80))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reason: Mapped[str] = mapped_column(String(255))
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthorizationDecision(Base):
    __tablename__ = "authorization_decisions"
    __table_args__ = (
        Index("ix_authorization_decision_actor_time", "user_id", "occurred_at"),
        Index("ix_authorization_decision_correlation", "correlation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    permission_key: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decision_code: Mapped[str] = mapped_column(String(80))
    scope_type: Mapped[str | None] = mapped_column(String(40))
    scope_hash: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    sources_json: Mapped[list | None] = mapped_column(JSON)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    access_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Origin(Base):
    __tablename__ = "origins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    description: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EventType(Base):
    __tablename__ = "event_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status in ('aberto','concluido','cancelado')", name="status_allowed"),
        Index("ix_appointments_date_status", "exam_date", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    renach: Mapped[str | None] = mapped_column(String(20), index=True)
    exam_date: Mapped[date] = mapped_column(Date, index=True)
    event_type_id: Mapped[int | None] = mapped_column(ForeignKey("event_types.id"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id"))
    psychologist_id: Mapped[int | None] = mapped_column(ForeignKey("professionals.id"))
    origin_id: Mapped[int | None] = mapped_column(ForeignKey("origins.id"))
    status: Mapped[str] = mapped_column(String(20), default=AppointmentStatus.OPEN.value)
    result: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    workflow_status: Mapped[str] = mapped_column(
        String(40), default="PAGAMENTO_PENDENTE", server_default="PAGAMENTO_PENDENTE"
    )
    reanalysis_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    operational_observation: Mapped[str | None] = mapped_column(Text)
    service_type_id: Mapped[int | None] = mapped_column(ForeignKey("service_types.id"), index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    operational_status: Mapped[str] = mapped_column(
        String(30), default="SCHEDULED", server_default="SCHEDULED", nullable=False
    )
    source_kind: Mapped[str] = mapped_column(
        String(20), default="LEGACY", server_default="LEGACY", nullable=False
    )
    source_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(50))
    missing_documents: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    finalized_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __mapper_args__ = {"version_id_col": row_version}


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="total_nonnegative"),
        CheckConstraint("status in ('pendente','pago','estornado')", name="status_allowed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING.value)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reversal_reason: Mapped[str | None] = mapped_column(String(255))
    reversed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    professional_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    clinic_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    __mapper_args__ = {"version_id_col": row_version}


class PaymentItem(TimestampMixin, Base):
    __tablename__ = "payment_items"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class FinancialAccount(TimestampMixin, Base):
    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FinancialMovement(TimestampMixin, Base):
    __tablename__ = "financial_movements"
    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="debit_nonnegative"),
        CheckConstraint("credit_amount >= 0", name="credit_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    movement_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    reference: Mapped[str | None] = mapped_column(String(100))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))


class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    receipt_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    issued_at: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    recipient_name: Mapped[str | None] = mapped_column(String(150))


class ClinicalDocument(TimestampMixin, Base):
    __tablename__ = "clinical_documents"
    __table_args__ = (UniqueConstraint("appointment_id", "document_type", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    workflow_status: Mapped[str] = mapped_column(
        String(30), default="PDF_AUTENTICADO", server_default="PDF_AUTENTICADO"
    )
    authenticated_at: Mapped[datetime | None] = mapped_column(DateTime)
    authenticated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class DocumentDelivery(TimestampMixin, Base):
    __tablename__ = "document_deliveries"
    __table_args__ = (
        CheckConstraint(
            "channel in ('telefone','whatsapp_manual','email_manual','presencial')",
            name="channel_allowed",
        ),
        Index("ix_document_deliveries_appointment_id", "appointment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_documents.id"))
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    delivered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(30))
    destination_masked: Mapped[str] = mapped_column(String(120))
    result: Mapped[str] = mapped_column(String(40))
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)


class AgendaImportBatch(TimestampMixin, Base):
    __tablename__ = "agenda_import_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    agenda_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), default="IMPORTED")
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime)
    rolled_back_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AgendaImportRow(TimestampMixin, Base):
    __tablename__ = "agenda_import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "source_row"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("agenda_import_batches.id", ondelete="CASCADE"), index=True
    )
    source_row: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    status: Mapped[str] = mapped_column(String(30), default="IMPORTED")


class LegacyRawRecord(Base):
    __tablename__ = "legacy_raw_records"
    __table_args__ = (
        UniqueConstraint("source_file", "source_row"),
        Index("ix_legacy_raw_table_hash", "source_table", "record_sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(255))
    source_table: Mapped[str] = mapped_column(String(80), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    record_sha256: Mapped[str] = mapped_column(String(64))
    deleted_in_source: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_json: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class LegacyImportMap(Base):
    __tablename__ = "legacy_import_map"
    __table_args__ = (
        UniqueConstraint("source_table", "source_key", "target_table"),
        Index("ix_import_map_target", "target_table", "target_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_table: Mapped[str] = mapped_column(String(80))
    source_key: Mapped[str] = mapped_column(String(120))
    target_table: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[int] = mapped_column(BigInteger)
    record_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class MigrationIssue(Base):
    __tablename__ = "migration_issues"
    __table_args__ = (Index("ix_migration_issue_status", "status", "severity"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_table: Mapped[str] = mapped_column(String(80))
    source_key: Mapped[str | None] = mapped_column(String(120))
    field_name: Mapped[str | None] = mapped_column(String(80))
    issue_code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="aberto")
    details_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
