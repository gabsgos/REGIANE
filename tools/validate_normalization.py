from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    LegacyImportMap,
    LegacyRawRecord,
    MigrationIssue,
    Patient,
    Payment,
    Receipt,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from tools.normalize_legacy import clean, parse_date

OUTPUT = Path("docs/fase_5_validacao.json")


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as session:
        candidate_rows = list(
            session.scalars(
                select(LegacyRawRecord)
                .where(LegacyRawRecord.source_file == "CANDIDAT.DBF")
                .order_by(LegacyRawRecord.source_row)
            )
        )
        appointment_count = session.scalar(select(func.count()).select_from(Appointment)) or 0
        patient_count = session.scalar(select(func.count()).select_from(Patient)) or 0
        payment_total = session.scalar(select(func.sum(Payment.total_amount))) or Decimal("0.00")
        blank_legacy = (
            session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.legacy_code.is_(None))
            )
            or 0
        )
        distinct_legacy = (
            session.scalar(select(func.count(func.distinct(Appointment.legacy_code)))) or 0
        )
        appointment_maps = (
            session.scalar(
                select(func.count())
                .select_from(LegacyImportMap)
                .where(
                    LegacyImportMap.source_table == "CANDIDAT",
                    LegacyImportMap.target_table == "appointments",
                )
            )
            or 0
        )
        receipt_count = session.scalar(select(func.count()).select_from(Receipt)) or 0
        issues = Counter(session.scalars(select(MigrationIssue.issue_code)))

        sample_rows = candidate_rows[:: max(1, len(candidate_rows) // 25)][:25]
        sample_matches = 0
        for row in sample_rows:
            payload = row.payload_json
            appointment = session.scalar(
                select(Appointment).where(Appointment.legacy_code == clean(payload.get("CODIGO")))
            )
            if not appointment:
                continue
            expected_date = parse_date(payload.get("DT_DIA")) or parse_date(
                payload.get("DT_USUARIO")
            )
            patient = session.get(Patient, appointment.patient_id)
            if (
                patient
                and patient.name == clean(payload.get("NOME"), 120)
                and appointment.exam_date == expected_date
            ):
                sample_matches += 1

    criteria = {
        "all_candidates_became_appointments": appointment_count == len(candidate_rows) == 3867,
        "all_appointments_have_unique_legacy_code": blank_legacy == 0
        and distinct_legacy == appointment_count,
        "candidate_appointment_map_complete": appointment_maps == appointment_count,
        "patient_consolidation_controlled": patient_count == 3808,
        "financial_total_reconciled": payment_total == Decimal("409829.41"),
        "receipt_mapping_or_review_complete": receipt_count
        + issues["ATENDIMENTO_RECIBO_NAO_ENCONTRADO"]
        == 3734,
        "deterministic_sample_matches": sample_matches == len(sample_rows) == 25,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_rows": len(candidate_rows),
        "patients": patient_count,
        "appointments": appointment_count,
        "appointment_maps": appointment_maps,
        "payment_total": str(payment_total),
        "receipts": receipt_count,
        "issue_counts": dict(sorted(issues.items())),
        "sample_size": len(sample_rows),
        "sample_matches": sample_matches,
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
