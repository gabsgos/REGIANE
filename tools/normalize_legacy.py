from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    ClinicalDocument,
    EventType,
    FinancialAccount,
    FinancialMovement,
    LegacyImportMap,
    LegacyRawRecord,
    MigrationIssue,
    Origin,
    Patient,
    Payment,
    PaymentItem,
    Professional,
    Receipt,
    Role,
    User,
    UserRole,
)
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

OUTPUT = Path("docs/fase_5_reconciliacao.json")


def clean(value: Any, limit: int | None = None) -> str:
    result = str(value or "").strip()
    return result[:limit] if limit else result


def digits(value: Any) -> str:
    return re.sub(r"\D", "", clean(value))


def name_key(value: Any) -> str:
    return " ".join(clean(value).upper().split())


def parse_date(value: Any) -> date | None:
    raw = clean(value)
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def money(value: Any) -> Decimal:
    raw = clean(value)
    if not raw:
        return Decimal("0.00")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def source_rows(session: Session, filename: str) -> list[LegacyRawRecord]:
    return list(
        session.scalars(
            select(LegacyRawRecord)
            .where(
                LegacyRawRecord.source_file == filename,
                LegacyRawRecord.deleted_in_source.is_(False),
            )
            .order_by(LegacyRawRecord.source_row)
        )
    )


def clear_normalized(session: Session) -> None:
    for model in (
        PaymentItem,
        Payment,
        ClinicalDocument,
        Receipt,
        FinancialMovement,
        AuditLog,
        AuthSession,
        UserRole,
        Appointment,
        User,
        Professional,
        Patient,
        FinancialAccount,
        Origin,
        EventType,
        LegacyImportMap,
        MigrationIssue,
        Role,
    ):
        session.execute(delete(model))


def add_map(
    session: Session,
    row: LegacyRawRecord,
    source_key: str,
    target_table: str,
    target_id: int,
) -> None:
    session.add(
        LegacyImportMap(
            source_table=row.source_table,
            source_key=f"{row.source_file}:{source_key}",
            target_table=target_table,
            target_id=target_id,
            record_sha256=row.record_sha256,
            imported_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )


def add_issue(
    session: Session,
    row: LegacyRawRecord,
    code: str,
    field: str | None,
    severity: str = "aviso",
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        MigrationIssue(
            source_table=row.source_table,
            source_key=f"{row.source_file}:{row.source_row}",
            field_name=field,
            issue_code=code,
            severity=severity,
            status="aberto",
            details_json=details,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )


def normalize(session: Session) -> dict[str, Any]:
    clear_normalized(session)
    roles = {
        name: Role(name=name, description=description)
        for name, description in (
            ("gerente", "Administracao e financeiro"),
            ("atendente", "Atendimento e recebimento"),
            ("medico", "Operacao clinica"),
        )
    }
    session.add_all(roles.values())
    session.flush()

    origin_by_code: dict[str, Origin] = {}
    for row in source_rows(session, "ORIGEM.DBF"):
        payload = row.payload_json
        code = clean(payload.get("CODIGO"), 20)
        item = Origin(
            legacy_code=code or None,
            description=clean(payload.get("DESCRICAO"), 100) or "Sem descricao",
            active=clean(payload.get("ATIVA")).upper() not in {"N", "0"},
        )
        session.add(item)
        session.flush()
        origin_by_code[code] = item
        add_map(session, row, str(row.source_row), "origins", item.id)

    event_by_code: dict[str, EventType] = {}
    for row in source_rows(session, "EVENTOS.DBF"):
        payload = row.payload_json
        code = clean(payload.get("CODIGO"), 20)
        item = EventType(
            legacy_code=code or None,
            name=clean(payload.get("NOMENCLATU"), 100) or "Sem descricao",
            active=True,
        )
        session.add(item)
        session.flush()
        event_by_code[code] = item
        add_map(session, row, str(row.source_row), "event_types", item.id)

    professional_by_key: dict[tuple[str, str], Professional] = {}
    for row in source_rows(session, "DR_MED.DBF"):
        payload = row.payload_json
        role = clean(payload.get("MED_PSI")).upper()
        council_type = "CRP" if role == "P" else "CRM"
        council_number = clean(payload.get("CRM") or payload.get("CREDENC"), 20)
        item = Professional(
            name=clean(payload.get("NOME"), 120) or "Profissional legado",
            council_type=council_type,
            council_number=council_number or f"LEGACY-{row.source_row}",
            council_region=clean(payload.get("REGIAO"), 5) or None,
            cpf=digits(payload.get("CPF"))[:11] or None,
            specialty="psicologia" if role == "P" else "medicina",
            active=clean(payload.get("ATIVO")).upper() not in {"N", "0"},
        )
        session.add(item)
        session.flush()
        professional_by_key[(council_type, council_number)] = item
        add_map(session, row, str(row.source_row), "professionals", item.id)

    user_by_legacy: dict[str, User] = {}
    for row in source_rows(session, "USUARIOS.DBF"):
        payload = row.payload_json
        code = clean(payload.get("COD_USER")) or str(row.source_row)
        item = User(
            username=f"legacy-{code}",
            display_name=clean(payload.get("NOME"), 120) or f"Usuario {code}",
            password_hash=None,
            cpf=digits(payload.get("CPF"))[:11] or None,
            phone=clean(payload.get("CELULAR"), 20) or None,
            active=clean(payload.get("DESATIVA")).upper() not in {"S", "1"},
            must_reset_password=True,
        )
        session.add(item)
        session.flush()
        manager = clean(payload.get("AC_ESTAT")).upper() in {"S", "1"}
        session.add(
            UserRole(user_id=item.id, role_id=roles["gerente" if manager else "atendente"].id)
        )
        user_by_legacy[code] = item
        add_map(session, row, code, "users", item.id)

    patient_by_cpf: dict[str, Patient] = {}
    appointment_by_code: dict[str, Appointment] = {}
    appointments_by_name: dict[str, list[Appointment]] = {}
    candidate_rows = source_rows(session, "CANDIDAT.DBF")
    for row in candidate_rows:
        payload = row.payload_json
        legacy_code = clean(payload.get("CODIGO"), 20)
        cpf_value = digits(payload.get("CPF"))
        valid_cpf = cpf_value if len(cpf_value) == 11 else ""
        patient = patient_by_cpf.get(valid_cpf) if valid_cpf else None
        if patient is None:
            patient = Patient(
                cpf=valid_cpf or None,
                name=clean(payload.get("NOME"), 120) or "Paciente sem nome",
                birth_date=parse_date(payload.get("DT_NASC")),
                phone=clean(payload.get("CONTATO"), 20) or None,
                email=clean(payload.get("EMAIL"), 254) or None,
                address_json={
                    "logradouro": clean(payload.get("LOGRAD")),
                    "numero": clean(payload.get("NUMERO")),
                    "complemento": clean(payload.get("COMPL")),
                    "bairro": clean(payload.get("BAIRRO")),
                    "cidade": clean(payload.get("CIDADE")),
                    "uf": clean(payload.get("ESTADOC")),
                    "cep": clean(payload.get("CEP")),
                },
                active=True,
            )
            session.add(patient)
            session.flush()
            if valid_cpf:
                patient_by_cpf[valid_cpf] = patient
        if not valid_cpf:
            add_issue(session, row, "CPF_AUSENTE_OU_INVALIDO", "CPF")
        add_map(session, row, legacy_code, "patients", patient.id)

        exam_date = parse_date(payload.get("DT_DIA"))
        if exam_date is None:
            exam_date = parse_date(payload.get("DT_USUARIO")) or date(1970, 1, 1)
            add_issue(
                session,
                row,
                "DATA_EXAME_SUBSTITUIDA",
                "DT_DIA",
                details={"regra": "fallback_DT_USUARIO_ou_1970-01-01"},
            )
        crm = clean(payload.get("CRM"), 20)
        crp = clean(payload.get("CRP"), 20)
        appointment = Appointment(
            patient_id=patient.id,
            legacy_code=legacy_code,
            renach=clean(payload.get("RENACH") or payload.get("NRO_RENACH"), 20) or None,
            exam_date=exam_date,
            event_type_id=event_by_code.get(clean(payload.get("USO"))).id
            if event_by_code.get(clean(payload.get("USO")))
            else None,
            doctor_id=professional_by_key.get(("CRM", crm)).id
            if professional_by_key.get(("CRM", crm))
            else None,
            psychologist_id=professional_by_key.get(("CRP", crp)).id
            if professional_by_key.get(("CRP", crp))
            else None,
            origin_id=origin_by_code.get(clean(payload.get("ORIGEM"))).id
            if origin_by_code.get(clean(payload.get("ORIGEM")))
            else None,
            status="concluido" if clean(payload.get("RESULT")) else "aberto",
            result=clean(payload.get("RESULT"), 100) or None,
            notes=clean(payload.get("OBSERVACAO")) or None,
            created_by_id=user_by_legacy.get(clean(payload.get("USUARIO"))).id
            if user_by_legacy.get(clean(payload.get("USUARIO")))
            else None,
        )
        session.add(appointment)
        session.flush()
        appointment_by_code[legacy_code] = appointment
        appointments_by_name.setdefault(name_key(payload.get("NOME")), []).append(appointment)
        add_map(session, row, legacy_code, "appointments", appointment.id)

    payment_source_total = Decimal("0.00")
    orphan_finance = 0
    payment_count = 0
    for row in source_rows(session, "PAGTOS.DBF"):
        payload = row.payload_json
        appointment = appointment_by_code.get(clean(payload.get("ALUNO")))
        if appointment is None:
            orphan_finance += 1
            add_issue(session, row, "ATENDIMENTO_FINANCEIRO_NAO_ENCONTRADO", "ALUNO", "erro")
            continue
        amount = money(payload.get("VALOR_PG"))
        if amount == 0:
            amount = money(payload.get("VALOR"))
        if amount < 0:
            add_issue(session, row, "VALOR_NEGATIVO", "VALOR_PG", "erro")
            continue
        status = "pago" if parse_date(payload.get("DT_PAGTO")) else "pendente"
        payment = Payment(
            appointment_id=appointment.id,
            total_amount=amount,
            status=status,
            paid_at=datetime.combine(parse_date(payload.get("DT_PAGTO")), datetime.min.time())
            if parse_date(payload.get("DT_PAGTO"))
            else None,
            created_by_id=user_by_legacy.get(clean(payload.get("USUARIO"))).id
            if user_by_legacy.get(clean(payload.get("USUARIO")))
            else None,
        )
        session.add(payment)
        session.flush()
        method = "cartao" if clean(payload.get("CARTAO")) else "dinheiro"
        if amount > 0:
            session.add(PaymentItem(payment_id=payment.id, method=method, amount=amount))
        add_map(session, row, str(row.source_row), "payments", payment.id)
        payment_source_total += amount
        payment_count += 1

    auxiliary_coverage: dict[str, int] = {}
    for filename in ("DEPOS.DBF", "L_CARTAO.DBF", "PROGCART.DBF"):
        covered = 0
        for row in source_rows(session, filename):
            appointment = appointment_by_code.get(clean(row.payload_json.get("ALUNO")))
            if appointment:
                add_map(session, row, str(row.source_row), "appointments", appointment.id)
                covered += 1
            else:
                orphan_finance += 1
                add_issue(session, row, "ATENDIMENTO_FINANCEIRO_NAO_ENCONTRADO", "ALUNO")
        auxiliary_coverage[filename] = covered

    receipt_count = 0
    for row in source_rows(session, "RECIBO.DBF"):
        payload = row.payload_json
        receipt_date = parse_date(payload.get("DT_RECIBO"))
        candidates = appointments_by_name.get(name_key(payload.get("ALUNO")), [])
        exact_date = [
            item for item in candidates if receipt_date and item.exam_date == receipt_date
        ]
        appointment = exact_date[0] if exact_date else None
        if appointment is None and candidates:
            appointment = min(
                candidates,
                key=lambda item: (
                    abs((item.exam_date - receipt_date).days) if receipt_date else item.id
                ),
            )
        if appointment is None:
            add_issue(
                session,
                row,
                "ATENDIMENTO_RECIBO_NAO_ENCONTRADO",
                "ALUNO",
                details={"regra": "nome_normalizado_e_data"},
            )
            continue
        item = Receipt(
            receipt_number=clean(payload.get("NRO_RECIBO"), 30) or f"LEGACY-{row.source_row}",
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            issued_at=receipt_date or appointment.exam_date,
            amount=money(payload.get("VALOR")),
            recipient_name=clean(payload.get("ALUNO"), 150) or None,
        )
        session.add(item)
        session.flush()
        add_map(session, row, str(row.source_row), "receipts", item.id)
        receipt_count += 1

    account_by_code: dict[str, FinancialAccount] = {}
    movement_count = 0
    for row in source_rows(session, "LANCTO.DBF"):
        payload = row.payload_json
        account_code = clean(payload.get("CONTA"), 20) or "SEM-CONTA"
        account = account_by_code.get(account_code)
        if account is None:
            account = FinancialAccount(
                legacy_code=account_code, name=f"Conta legado {account_code}"
            )
            session.add(account)
            session.flush()
            account_by_code[account_code] = account
        appointment = appointment_by_code.get(clean(payload.get("REFERENCIA")))
        item = FinancialMovement(
            account_id=account.id,
            movement_date=parse_date(payload.get("DATA")) or date(1970, 1, 1),
            description=clean(payload.get("HISTORICO"), 255) or None,
            debit_amount=max(money(payload.get("DEBITO")), Decimal("0.00")),
            credit_amount=max(money(payload.get("CREDITO")), Decimal("0.00")),
            reference=clean(payload.get("REFERENCIA"), 100) or None,
            appointment_id=appointment.id if appointment else None,
        )
        session.add(item)
        session.flush()
        add_map(session, row, str(row.source_row), "financial_movements", item.id)
        movement_count += 1

    session.flush()
    database_payment_total = session.scalar(select(func.sum(Payment.total_amount))) or Decimal(
        "0.00"
    )
    return {
        "patients": session.scalar(select(func.count()).select_from(Patient)),
        "appointments": session.scalar(select(func.count()).select_from(Appointment)),
        "professionals": session.scalar(select(func.count()).select_from(Professional)),
        "users": session.scalar(select(func.count()).select_from(User)),
        "payments": payment_count,
        "receipts": receipt_count,
        "financial_movements": movement_count,
        "legacy_maps": session.scalar(select(func.count()).select_from(LegacyImportMap)),
        "migration_issues": session.scalar(select(func.count()).select_from(MigrationIssue)),
        "payment_source_total": str(payment_source_total),
        "payment_database_total": str(database_payment_total),
        "payment_totals_match": payment_source_total == database_payment_total,
        "orphan_financial_rows": orphan_finance,
        "auxiliary_financial_coverage": auxiliary_coverage,
    }


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    started = time.perf_counter()
    with Session(engine) as session, session.begin():
        result = normalize(session)
    result.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    )
    result["integrity"] = "PASS" if result["payment_totals_match"] else "FAIL"
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
