from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from backend.app.core.config import get_settings
from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base
from sqlalchemy import CheckConstraint, create_engine, inspect, text

OUTPUT = Path("docs/fase_3_validacao_schema.json")


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    expected_revision = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    inspector = inspect(engine)
    expected = set(Base.metadata.tables)
    expected_foreign_keys = sum(len(table.foreign_keys) for table in Base.metadata.tables.values())
    expected_checks = sum(
        sum(isinstance(item, CheckConstraint) for item in table.constraints)
        for table in Base.metadata.tables.values()
    )
    actual = set(inspector.get_table_names())
    domain_actual = actual - {"alembic_version"}

    foreign_keys = sum(len(inspector.get_foreign_keys(table)) for table in domain_actual)
    checks = sum(len(inspector.get_check_constraints(table)) for table in domain_actual)

    with engine.connect() as connection:
        version = connection.execute(text("SELECT VERSION()")).scalar_one()
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        table_options = (
            connection.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
                )
            )
            .mappings()
            .all()
        )

    all_innodb = all(row["ENGINE"] == "InnoDB" for row in table_options)
    all_utf8mb4 = all(
        (row["TABLE_COLLATION"] or "").lower().startswith("utf8mb4") for row in table_options
    )
    numeric_columns = {
        f"{table}.{column['name']}": str(column["type"])
        for table in ("payments", "payment_items", "financial_movements", "receipts")
        for column in inspector.get_columns(table)
        if column["name"] in {"total_amount", "amount", "debit_amount", "credit_amount"}
    }
    numeric_ok = all("DECIMAL(12, 2)" in value for value in numeric_columns.values())

    criteria = {
        "expected_tables_match": domain_actual == expected,
        "no_unexpected_tables": not (domain_actual - expected),
        "foreign_keys_match_model": foreign_keys == expected_foreign_keys,
        "check_constraints_match_model": checks == expected_checks,
        "all_tables_innodb": all_innodb,
        "all_tables_utf8mb4": all_utf8mb4,
        "financial_columns_decimal_12_2": numeric_ok,
        "alembic_revision_at_head": revision == expected_revision,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": engine.url.database,
        "mysql_version": version,
        "alembic_revision": revision,
        "expected_alembic_revision": expected_revision,
        "expected_table_count": len(expected),
        "actual_domain_table_count": len(domain_actual),
        "foreign_key_count": foreign_keys,
        "expected_foreign_key_count": expected_foreign_keys,
        "check_constraint_count": checks,
        "expected_check_constraint_count": expected_checks,
        "numeric_columns": numeric_columns,
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
