import json
from datetime import UTC, datetime
from pathlib import Path

from tools.final_release_gate import evaluate

NOW = datetime(2026, 11, 1, 19, 10, tzinfo=UTC)


def write_json(root: Path, relative_path: str, value: dict) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def valid_release_tree(root: Path) -> None:
    (root / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
    write_json(root, "docs/fase_14_resultado.json", {"status": "APROVADA"})
    write_json(root, "docs/homologation_validation.json", {"status": "APPROVED"})
    write_json(
        root,
        "docs/fase_15_resultado.json",
        {
            "integrity": "PASS",
            "production_active": True,
            "legacy_read_only": True,
            "data_loss_detected": False,
        },
    )
    write_json(root, "docs/smoke_test_result.json", {"integrity": "PASS"})
    write_json(
        root,
        "docs/fase_15_backup_pos_corte.json",
        {"integrity": "PASS", "restore_tested": True},
    )
    write_json(
        root,
        "docs/fase_16_validacao_final.json",
        {"integrity": "PASS", "critical_defects": 0, "high_defects": 0},
    )
    write_json(root, "docs/release_manifest_final.json", {"integrity": "PASS"})
    write_json(
        root,
        "docs/auditoria_seguranca_resultado.json",
        {"decision": "TECHNICAL_SECURITY_PREFLIGHT_PASS", "project_version": "1.0.0"},
    )


def test_complete_release_evidence_is_go(tmp_path: Path) -> None:
    valid_release_tree(tmp_path)
    result = evaluate(tmp_path, NOW)
    assert result["decision"] == "GO_FINAL_1_0_0"
    assert result["failed_criteria"] == []


def test_missing_human_and_cutover_evidence_fails_closed(tmp_path: Path) -> None:
    valid_release_tree(tmp_path)
    write_json(tmp_path, "docs/homologation_validation.json", {"status": "NO_GO"})
    write_json(tmp_path, "docs/fase_15_resultado.json", {"integrity": "PENDING"})
    result = evaluate(tmp_path, NOW)
    assert result["decision"] == "NO_GO"
    assert "human_homologation" in result["failed_criteria"]
    assert "cutover_integrity" in result["failed_criteria"]
    assert "production_active" in result["failed_criteria"]
    assert "legacy_read_only" in result["failed_criteria"]
