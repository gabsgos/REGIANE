from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pymysql
from backend.app.core.config import get_settings
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import make_url

REPORT = Path("docs/fase_13_ensaio_completo.json")
DATABASE = "abel_rehearsal_test"
ROOT_SECRET = Path("data/mysql-root.secret")
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


def root_connection():
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password=ROOT_SECRET.read_text(encoding="utf-8").strip(),
        charset="utf8mb4",
        autocommit=True,
    )


def main() -> int:
    settings = get_settings()
    production_url = settings.database_url
    if not production_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    parsed = make_url(production_url)
    rehearsal_url = parsed.set(database=DATABASE).render_as_string(hide_password=False)
    production_before = counts(production_url)
    username = (parsed.username or "abel_app").replace("'", "''")
    with root_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
        cursor.execute(
            f"CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        cursor.execute(f"GRANT ALL PRIVILEGES ON `{DATABASE}`.* TO '{username}'@'localhost'")

    commands = [
        ("migrations_from_zero", ["alembic", "upgrade", "head"]),
        ("schema_integrity", ["python", "-m", "tools.validate_schema"]),
        (
            "import_first",
            [
                "python",
                "-m",
                "tools.import_legacy",
                "--output",
                "docs/fase_13_importacao_primeira.json",
            ],
        ),
        (
            "import_repeat",
            [
                "python",
                "-m",
                "tools.import_legacy",
                "--output",
                "docs/fase_13_importacao_repetida.json",
            ],
        ),
        ("normalize_first", ["python", "-m", "tools.normalize_legacy"]),
        ("normalize_repeat", ["python", "-m", "tools.normalize_legacy"]),
        ("normalization_integrity", ["python", "-m", "tools.validate_normalization"]),
        ("clinical_api", ["python", "-m", "tools.validate_clinical_api"]),
        ("finance_api", ["python", "-m", "tools.validate_finance_api"]),
        ("documents_api", ["python", "-m", "tools.validate_documents_api"]),
        ("admin_reports", ["python", "-m", "tools.validate_admin_reports"]),
        (
            "concurrency_performance",
            ["python", "-m", "tools.validate_concurrency_performance"],
        ),
        ("frontend", ["python", "-m", "tools.validate_frontend"]),
        ("alembic_drift", ["alembic", "check"]),
    ]
    env = os.environ.copy()
    env["ABEL_DATABASE_URL"] = rehearsal_url
    results: list[dict] = []
    overall_start = time.perf_counter()
    failure: str | None = None
    rehearsal_counts: dict[str, int] = {}
    try:
        for name, arguments in commands:
            started = time.perf_counter()
            process = subprocess.run(
                [str(POETRY), "run", *arguments],
                cwd=Path.cwd(),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            result = {
                "name": name,
                "return_code": process.returncode,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "status": "PASS" if process.returncode == 0 else "FAIL",
            }
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if process.returncode != 0:
                failure = name
                break
        rehearsal_counts = counts(rehearsal_url) if failure is None else {}
    finally:
        with root_connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")

    production_after = counts(production_url)
    criteria = {
        "all_steps_pass": failure is None and all(item["status"] == "PASS" for item in results),
        "production_unchanged": production_before == production_after,
        "rehearsal_database_removed": True,
        "expected_normalized_appointments": rehearsal_counts.get("appointments") == 3867,
        "expected_staging_rows": rehearsal_counts.get("legacy_raw_records") == 296775,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": DATABASE,
        "steps": results,
        "duration_seconds": round(time.perf_counter() - overall_start, 3),
        "failure": failure,
        "rehearsal_table_counts": rehearsal_counts,
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"criteria": criteria, "integrity": result["integrity"]}, indent=2))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
