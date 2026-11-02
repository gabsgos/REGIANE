from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_APPROVAL = Path("data/homologation_approval.json")
DEFAULT_REPORT = Path("docs/homologation_validation.json")
EVIDENCE_FILES = {
    "pilot_sha256": Path("docs/fase_14_piloto_tecnico.json"),
    "cut_plan_sha256": Path("docs/plano_corte_retorno.md"),
}
REQUIRED_ROLES = {"gerencia", "atendimento", "medico_psicologo"}
PLACEHOLDERS = {"", "PREENCHER", "NOME", "RESPONSAVEL", "EXEMPLO"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_aware_datetime(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{field}: data ISO 8601 obrigatoria")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field}: data ISO 8601 invalida")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field}: fuso horario obrigatorio")
        return None
    return parsed


def valid_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value.strip()) >= 3
        and value.strip().upper() not in PLACEHOLDERS
    )


def validate_payload(
    payload: dict[str, Any], expected_hashes: dict[str, str], now: datetime
) -> dict[str, Any]:
    errors: list[str] = []
    approvals = payload.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
        errors.append("approvals: lista obrigatoria")

    seen_roles: set[str] = set()
    for index, approval in enumerate(approvals):
        prefix = f"approvals[{index}]"
        if not isinstance(approval, dict):
            errors.append(f"{prefix}: objeto obrigatorio")
            continue
        role = approval.get("role")
        if role not in REQUIRED_ROLES:
            errors.append(f"{prefix}.role: perfil invalido")
        elif role in seen_roles:
            errors.append(f"{prefix}.role: perfil duplicado")
        else:
            seen_roles.add(role)
        if not valid_name(approval.get("responsible_name")):
            errors.append(f"{prefix}.responsible_name: nome real obrigatorio")
        if approval.get("approved") is not True:
            errors.append(f"{prefix}.approved: deve ser true")
        approved_at = parse_aware_datetime(
            approval.get("approved_at"), f"{prefix}.approved_at", errors
        )
        if approved_at and approved_at > now + timedelta(minutes=5):
            errors.append(f"{prefix}.approved_at: aprovacao nao pode estar no futuro")
        if not isinstance(approval.get("workflows_validated"), list) or not approval.get(
            "workflows_validated"
        ):
            errors.append(f"{prefix}.workflows_validated: ao menos um fluxo obrigatorio")

    missing_roles = sorted(REQUIRED_ROLES - seen_roles)
    if missing_roles:
        errors.append("approvals: perfis ausentes: " + ", ".join(missing_roles))

    cutover = payload.get("cutover")
    if not isinstance(cutover, dict):
        cutover = {}
        errors.append("cutover: objeto obrigatorio")
    if cutover.get("plan_approved") is not True:
        errors.append("cutover.plan_approved: deve ser true")
    if not valid_name(cutover.get("operational_responsible")):
        errors.append("cutover.operational_responsible: nome real obrigatorio")
    if not valid_name(cutover.get("rollback_responsible")):
        errors.append("cutover.rollback_responsible: nome real obrigatorio")
    window_start = parse_aware_datetime(cutover.get("window_start"), "cutover.window_start", errors)
    window_end = parse_aware_datetime(cutover.get("window_end"), "cutover.window_end", errors)
    if window_start and window_end and window_end <= window_start:
        errors.append("cutover: fim da janela deve ser posterior ao inicio")
    if not valid_name(payload.get("change_control_id")):
        errors.append("change_control_id: identificador real obrigatorio")
    if payload.get("operator_confirmation") is not True:
        errors.append("operator_confirmation: deve ser true")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
        errors.append("evidence: objeto obrigatorio")
    hash_checks: dict[str, bool] = {}
    for key, expected in expected_hashes.items():
        provided = evidence.get(key)
        match = isinstance(provided, str) and provided.lower() == expected.lower()
        hash_checks[key] = match
        if not match:
            errors.append(f"evidence.{key}: hash nao confere")

    return {
        "generated_at": now.astimezone(UTC).isoformat(),
        "status": "APPROVED" if not errors else "NO_GO",
        "criteria": {
            "required_roles": sorted(REQUIRED_ROLES),
            "roles_present": sorted(seen_roles),
            "evidence_hashes": hash_checks,
            "cutover_plan_approved": cutover.get("plan_approved") is True,
            "operator_confirmation": payload.get("operator_confirmation") is True,
        },
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida a homologacao humana da Fase 14")
    parser.add_argument("--approval", type=Path, default=DEFAULT_APPROVAL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_hashes = {key: sha256_file(path) for key, path in EVIDENCE_FILES.items()}
    if args.approval.is_file():
        payload = json.loads(args.approval.read_text(encoding="utf-8"))
        report = validate_payload(payload, expected_hashes, datetime.now(UTC))
    else:
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "NO_GO",
            "criteria": {"approval_file": str(args.approval), "exists": False},
            "errors": ["Arquivo local de homologacao nao encontrado"],
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "APPROVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
