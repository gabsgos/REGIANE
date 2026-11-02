from datetime import UTC, datetime

from tools.validate_homologation import validate_payload

NOW = datetime(2026, 10, 31, 16, 30, tzinfo=UTC)
HASHES = {"pilot_sha256": "a" * 64, "cut_plan_sha256": "b" * 64}


def valid_payload() -> dict:
    return {
        "change_control_id": "ABEL-CORTE-001",
        "operator_confirmation": True,
        "approvals": [
            {
                "role": role,
                "responsible_name": name,
                "approved": True,
                "approved_at": "2026-10-31T13:00:00-03:00",
                "workflows_validated": ["fluxo real"],
            }
            for role, name in (
                ("gerencia", "Gestor Real"),
                ("atendimento", "Atendente Real"),
                ("medico_psicologo", "Profissional Real"),
            )
        ],
        "cutover": {
            "plan_approved": True,
            "window_start": "2026-11-01T20:00:00-03:00",
            "window_end": "2026-11-01T22:00:00-03:00",
            "operational_responsible": "Operador Real",
            "rollback_responsible": "Gestor Real",
        },
        "evidence": HASHES.copy(),
    }


def test_complete_homologation_is_approved() -> None:
    result = validate_payload(valid_payload(), HASHES, NOW)
    assert result["status"] == "APPROVED"
    assert result["errors"] == []


def test_missing_human_approval_fails_closed() -> None:
    payload = valid_payload()
    payload["approvals"][1]["approved"] = False
    payload["approvals"][2]["responsible_name"] = "PREENCHER"
    payload["evidence"]["cut_plan_sha256"] = "alterado"
    result = validate_payload(payload, HASHES, NOW)
    assert result["status"] == "NO_GO"
    assert len(result["errors"]) == 3
