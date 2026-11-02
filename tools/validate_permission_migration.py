from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pymysql
from backend.app.core.config import get_settings
from sqlalchemy.engine import URL, make_url

TEST_DATABASE = "abel_permissions_test"
ROOT_SECRET = Path("data/mysql-root.secret")
REPORT = Path("docs/permissoes_e06_migration_rehearsal.json")
COUNT_TABLES = (
    "users",
    "roles",
    "patients",
    "appointments",
    "payments",
    "receipts",
    "clinical_documents",
    "audit_logs",
)


def root_connection(database: str | None = None):
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password=ROOT_SECRET.read_text(encoding="utf-8").strip(),
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def mysql_tool(name: str) -> str:
    return str(Path(get_settings().mysql_bin_path) / f"{name}.exe")


def run_alembic(revision: str, database_url: str) -> None:
    env = os.environ.copy()
    env["ABEL_DATABASE_URL"] = database_url
    command = "upgrade" if revision != "2e32865e3947" else "downgrade"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic falhou para {revision}: {result.stderr[-1000:]}")


def counts(database: str) -> dict[str, int]:
    with root_connection(database) as connection, connection.cursor() as cursor:
        result = {}
        for table in COUNT_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            result[table] = int(cursor.fetchone()[0])
        return result


def table_exists(database: str, table: str) -> bool:
    with root_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema=%s AND table_name=%s",
            (database, table),
        )
        return bool(cursor.fetchone()[0])


def catalog_metrics(database: str) -> dict[str, int]:
    with root_connection(database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM permissions")
        permission_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(DISTINCT `key`) FROM permissions")
        unique_permissions = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM roles WHERE name IN ('gerente','atendente','medico')"
        )
        profile_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM role_permissions")
        assignment_count = int(cursor.fetchone()[0])
    return {
        "permissions": permission_count,
        "unique_permissions": unique_permissions,
        "profiles": profile_count,
        "profile_permission_assignments": assignment_count,
    }


def workflow_metrics(database: str) -> dict[str, int | bool]:
    with root_connection(database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='appointments' "
            "AND column_name IN ('workflow_status','reanalysis_required',"
            "'operational_observation')",
            (database,),
        )
        appointment_columns = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM appointments a WHERE a.status='aberto' "
            "AND (a.doctor_id IS NOT NULL OR a.psychologist_id IS NOT NULL) "
            "AND EXISTS (SELECT 1 FROM payments p WHERE p.appointment_id=a.id "
            "AND p.status='pago')"
        )
        expected_released = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM appointments WHERE workflow_status='LIBERADO_PARA_MEDICO'"
        )
        released = int(cursor.fetchone()[0])
    return {
        "appointment_workflow_columns": appointment_columns,
        "delivery_table_exists": table_exists(database, "document_deliveries"),
        "expected_released": expected_released,
        "released": released,
    }


def main() -> int:
    if not re.fullmatch(r"abel_permissions_test", TEST_DATABASE):
        raise RuntimeError("Nome do banco de teste invalido")
    source_url = make_url(get_settings().database_url or "")
    root_password = ROOT_SECRET.read_text(encoding="utf-8").strip()
    test_url = URL.create(
        "mysql+pymysql",
        username="root",
        password=root_password,
        host="127.0.0.1",
        port=3307,
        database=TEST_DATABASE,
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)
    tool_env = os.environ.copy()
    tool_env["MYSQL_PWD"] = root_password

    with tempfile.TemporaryDirectory(prefix="abel-permissions-") as temporary:
        dump = Path(temporary) / "source.sql"
        with root_connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{TEST_DATABASE}`")
            cursor.execute(
                f"CREATE DATABASE `{TEST_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        try:
            dumped = subprocess.run(
                [
                    mysql_tool("mysqldump"),
                    "--host=127.0.0.1",
                    "--port=3307",
                    "--user=root",
                    "--single-transaction",
                    "--default-character-set=utf8mb4",
                    f"--result-file={dump}",
                    source_url.database,
                ],
                env=tool_env,
                capture_output=True,
                text=True,
                check=False,
            )
            if dumped.returncode != 0:
                raise RuntimeError(f"Dump isolado falhou: {dumped.stderr[-1000:]}")
            with dump.open("rb") as stream:
                restored = subprocess.run(
                    [
                        mysql_tool("mysql"),
                        "--host=127.0.0.1",
                        "--port=3307",
                        "--user=root",
                        "--default-character-set=utf8mb4",
                        TEST_DATABASE,
                    ],
                    stdin=stream,
                    env=tool_env,
                    capture_output=True,
                    check=False,
                )
            if restored.returncode != 0:
                raise RuntimeError("Restauracao isolada falhou")

            baseline = counts(TEST_DATABASE)
            run_alembic("head", test_url)
            first_catalog = catalog_metrics(TEST_DATABASE)
            first_workflow = workflow_metrics(TEST_DATABASE)
            after_upgrade = counts(TEST_DATABASE)
            run_alembic("2e32865e3947", test_url)
            after_downgrade = counts(TEST_DATABASE)
            tables_removed = not table_exists(TEST_DATABASE, "permissions")
            run_alembic("head", test_url)
            second_catalog = catalog_metrics(TEST_DATABASE)
            second_workflow = workflow_metrics(TEST_DATABASE)
            after_second_upgrade = counts(TEST_DATABASE)
            criteria = {
                "baseline_preserved_first_upgrade": baseline == after_upgrade,
                "downgrade_preserved_data": baseline == after_downgrade,
                "new_tables_removed_on_downgrade": tables_removed,
                "baseline_preserved_second_upgrade": baseline == after_second_upgrade,
                "exactly_42_unique_permissions": first_catalog["permissions"]
                == first_catalog["unique_permissions"]
                == 42,
                "exactly_three_profiles": first_catalog["profiles"] == 3,
                "repeatable_catalog": first_catalog == second_catalog,
                "workflow_schema_complete": first_workflow[
                    "appointment_workflow_columns"
                ]
                == 3
                and first_workflow["delivery_table_exists"] is True,
                "workflow_backfill_consistent": first_workflow["expected_released"]
                == first_workflow["released"],
                "workflow_repeatable": first_workflow == second_workflow,
            }
        finally:
            with root_connection() as connection, connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{TEST_DATABASE}`")

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_database": source_url.database,
        "test_database": TEST_DATABASE,
        "baseline_counts": baseline,
        "catalog": second_catalog,
        "workflow": second_workflow,
        "criteria": criteria,
        "isolated_database_removed": not table_exists(TEST_DATABASE, "permissions"),
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
