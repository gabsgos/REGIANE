from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    Patient,
    Payment,
    PaymentItem,
    Receipt,
    User,
    UserRole,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session
from tools.validate_clinical_api import create_validation_user, login

OUTPUT = Path("docs/fase_8_validacao_financeira.json")


def decimal_method(summary: dict, method: str) -> Decimal:
    return Decimal(summary.get("by_method", {}).get(method, "0.00"))


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    suffix = secrets.token_hex(5)
    manager_name = f"finance-manager-{suffix}"
    doctor_name = f"finance-doctor-{suffix}"
    manager_password = secrets.token_urlsafe(18)
    doctor_password = secrets.token_urlsafe(18)
    with Session(engine) as session, session.begin():
        manager = create_validation_user(session, manager_name, manager_password, "gerente")
        doctor = create_validation_user(session, doctor_name, doctor_password, "medico")
        patient = Patient(name="Paciente Financeiro Validacao", active=True)
        session.add(patient)
        session.flush()
        appointment = Appointment(patient_id=patient.id, exam_date=date.today(), status="aberto")
        session.add(appointment)
        session.flush()
        manager_id, doctor_id = manager.id, doctor.id
        patient_id, appointment_id = patient.id, appointment.id

    client = TestClient(create_app())
    csrf = login(client, manager_name, manager_password)
    baseline = client.get("/api/finance/summary").json()
    mismatch = client.post(
        "/api/finance/payments",
        headers={"X-CSRF-Token": csrf},
        json={
            "appointment_id": appointment_id,
            "total_amount": "100.00",
            "items": [{"method": "pix", "amount": "99.00"}],
        },
    )
    negative = client.post(
        "/api/finance/payments",
        headers={"X-CSRF-Token": csrf},
        json={
            "appointment_id": appointment_id,
            "total_amount": "-1.00",
            "items": [{"method": "dinheiro", "amount": "-1.00"}],
        },
    )
    created = client.post(
        "/api/finance/payments",
        headers={"X-CSRF-Token": csrf},
        json={
            "appointment_id": appointment_id,
            "total_amount": "100.00",
            "items": [
                {"method": "pix", "amount": "60.00"},
                {"method": "dinheiro", "amount": "40.00"},
            ],
        },
    )
    created_json = created.json() if created.status_code == 201 else {}
    payment_id = created_json.get("id")
    after_payment = client.get("/api/finance/summary").json()
    receipt = client.post(
        "/api/finance/receipts",
        headers={"X-CSRF-Token": csrf},
        json={"appointment_id": appointment_id, "amount": "100.00"},
    )

    doctor_client = TestClient(create_app())
    login(doctor_client, doctor_name, doctor_password)
    doctor_denied = doctor_client.get(f"/api/finance/payments/{payment_id}")

    reversed_response = client.post(
        f"/api/finance/payments/{payment_id}/reverse",
        headers={"X-CSRF-Token": csrf},
        json={
            "reason": "Estorno controlado de validacao",
            "expected_version": created_json.get("row_version", 1),
        },
    )
    after_reversal = client.get("/api/finance/summary").json()
    persisted_payment = client.get(f"/api/finance/payments/{payment_id}")

    baseline_total = Decimal(baseline.get("paid_total", "0.00"))
    paid_total = Decimal(after_payment.get("paid_total", "0.00"))
    reversed_total = Decimal(after_reversal.get("paid_total", "0.00"))
    pix_delta = decimal_method(after_payment, "pix") - decimal_method(baseline, "pix")
    cash_delta = decimal_method(after_payment, "dinheiro") - decimal_method(baseline, "dinheiro")
    with Session(engine) as session:
        audit_count = (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.user_id == manager_id,
                    AuditLog.entity_type.in_(["payments", "receipts"]),
                )
            )
            or 0
        )

    criteria = {
        "mismatched_sum_rejected": mismatch.status_code == 422,
        "negative_value_rejected": negative.status_code == 422,
        "hybrid_payment_created": created.status_code == 201
        and len(created_json.get("items", [])) == 2,
        "summary_total_increment": paid_total - baseline_total == Decimal("100.00"),
        "summary_methods_increment": pix_delta == Decimal("60.00")
        and cash_delta == Decimal("40.00"),
        "receipt_created": receipt.status_code == 201,
        "doctor_finance_denied": doctor_denied.status_code == 403,
        "reversal_succeeds": reversed_response.status_code == 200,
        "reversal_removes_from_paid_totals": reversed_total == baseline_total,
        "original_payment_preserved": persisted_payment.status_code == 200
        and persisted_payment.json().get("status") == "estornado"
        and len(persisted_payment.json().get("items", [])) == 2,
        "financial_changes_audited": audit_count >= 3,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "audit_events": audit_count,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }

    with Session(engine) as session, session.begin():
        receipt_id = receipt.json().get("id") if receipt.status_code == 201 else None
        if receipt_id:
            session.execute(delete(Receipt).where(Receipt.id == receipt_id))
        if payment_id:
            session.execute(delete(PaymentItem).where(PaymentItem.payment_id == payment_id))
            session.execute(delete(Payment).where(Payment.id == payment_id))
        session.execute(delete(AuditLog).where(AuditLog.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(UserRole).where(UserRole.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.execute(delete(User).where(User.id.in_([manager_id, doctor_id])))
        session.execute(delete(Patient).where(Patient.id == patient_id))

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
