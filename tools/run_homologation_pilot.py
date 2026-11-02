from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select

REPORT = Path("docs/fase_14_piloto_tecnico.json")
POETRY = Path("C:/Program Files/Python311/Scripts/poetry.exe")


def counts(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url, pool_pre_ping=True)
    metadata = MetaData()
    with engine.connect() as connection:
        return {
            table_name: int(
                connection.scalar(
                    select(func.count()).select_from(
                        Table(table_name, metadata, autoload_with=connection)
                    )
                )
                or 0
            )
            for table_name in sorted(inspect(engine).get_table_names())
        }


def main() -> int:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    before = counts(database_url)
    commands = [
        ("atendimento_e_medico", "tools.validate_clinical_api"),
        ("financeiro", "tools.validate_finance_api"),
        ("laudos", "tools.validate_documents_api"),
        ("usuarios_e_relatorios", "tools.validate_admin_reports"),
        ("frontend", "tools.validate_frontend"),
    ]
    results: list[dict] = []
    for name, module in commands:
        started = time.perf_counter()
        process = subprocess.run(
            [str(POETRY), "run", "python", "-m", module],
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "workflow": name,
                "status": "PASS" if process.returncode == 0 else "FAIL",
                "duration_seconds": round(time.perf_counter() - started, 3),
            }
        )
        if process.returncode != 0:
            break
    after = counts(database_url)
    criteria = {
        "all_controlled_workflows_pass": len(results) == len(commands)
        and all(item["status"] == "PASS" for item in results),
        "production_counts_unchanged": before == after,
        "human_approval": False,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "workflows": results,
        "criteria": criteria,
        "technical_integrity": "PASS"
        if criteria["all_controlled_workflows_pass"] and criteria["production_counts_unchanged"]
        else "FAIL",
        "homologation_status": "PENDING_HUMAN_APPROVAL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["technical_integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
