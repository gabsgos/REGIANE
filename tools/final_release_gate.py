from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPORT = Path("docs/final_release_gate.json")


def read_json(root: Path, relative_path: str) -> dict[str, Any] | None:
    path = root / relative_path
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def project_version(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    value = data.get("project", {}).get("version")
    return value if isinstance(value, str) else None


def evaluate(root: Path, now: datetime | None = None) -> dict[str, Any]:
    phase_14 = read_json(root, "docs/fase_14_resultado.json") or {}
    homologation = read_json(root, "docs/homologation_validation.json") or {}
    phase_15 = read_json(root, "docs/fase_15_resultado.json") or {}
    smoke = read_json(root, "docs/smoke_test_result.json") or {}
    post_cut_backup = read_json(root, "docs/fase_15_backup_pos_corte.json") or {}
    final_validation = read_json(root, "docs/fase_16_validacao_final.json") or {}
    final_manifest = read_json(root, "docs/release_manifest_final.json") or {}
    security = read_json(root, "docs/auditoria_seguranca_resultado.json") or {}
    version = project_version(root)

    criteria = {
        "human_homologation": homologation.get("status") == "APPROVED",
        "phase_14_approved": phase_14.get("status") == "APROVADA",
        "cutover_integrity": phase_15.get("integrity") == "PASS",
        "production_active": phase_15.get("production_active") is True,
        "legacy_read_only": phase_15.get("legacy_read_only") is True,
        "no_data_loss": phase_15.get("data_loss_detected") is False,
        "post_cut_smoke": smoke.get("integrity") == "PASS",
        "post_cut_backup": post_cut_backup.get("integrity") == "PASS",
        "post_cut_restore": post_cut_backup.get("restore_tested") is True,
        "security_preflight": security.get("decision")
        == "TECHNICAL_SECURITY_PREFLIGHT_PASS",
        "security_current_version": security.get("project_version") == version,
        "final_tests": final_validation.get("integrity") == "PASS",
        "zero_critical_defects": final_validation.get("critical_defects") == 0,
        "zero_high_defects": final_validation.get("high_defects") == 0,
        "final_manifest": final_manifest.get("integrity") == "PASS",
        "final_version": version == "1.0.0",
        "no_build_txt": not (root / "build.txt").exists(),
    }
    failed = [name for name, passed in criteria.items() if not passed]
    generated_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    return {
        "generated_at": generated_at,
        "project_version": version,
        "criteria": criteria,
        "failed_criteria": failed,
        "decision": "GO_FINAL_1_0_0" if not failed else "NO_GO",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida o gate fail-closed da build final ABEL")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate(args.root.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["decision"] == "GO_FINAL_1_0_0" else 2


if __name__ == "__main__":
    raise SystemExit(main())
