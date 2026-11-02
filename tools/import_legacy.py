from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.db.models import LegacyRawRecord
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from tools.legacy_inventory import is_dbf_format, parse_layout


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    source_file: str
    source_table: str
    records: list[dict[str, Any]]
    sha256_before: str
    duration_seconds: float


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_field(raw: bytes) -> str:
    return raw.rstrip(b" \x00").decode("cp1252", errors="replace")


def read_fpt_memo(fpt_path: Path, raw_pointer: bytes) -> str | None:
    pointer_text = raw_pointer.strip().decode("ascii", errors="ignore")
    if not pointer_text or not pointer_text.isdigit() or not fpt_path.exists():
        return None
    pointer = int(pointer_text)
    if pointer <= 0:
        return None
    data = fpt_path.read_bytes()
    block_size = int.from_bytes(data[6:8], "big") if len(data) >= 8 else 0
    if block_size <= 0:
        block_size = 512
    offset = pointer * block_size
    if offset + 8 > len(data):
        return None
    length = int.from_bytes(data[offset + 4 : offset + 8], "big")
    content = data[offset + 8 : offset + 8 + length]
    return content.decode("cp1252", errors="replace").rstrip("\x00")


def parse_file(path: Path, source_root: Path) -> ParsedFile:
    started = time.perf_counter()
    before = file_sha256(path)
    layout = parse_layout(path)
    data = path.read_bytes()
    fpt_path = path.with_suffix(".fpt")
    records: list[dict[str, Any]] = []
    relative = path.relative_to(source_root).as_posix()

    for row_index in range(layout.declared_rows):
        start = layout.header_length + row_index * layout.record_length
        raw_record = data[start : start + layout.record_length]
        if len(raw_record) != layout.record_length:
            raise ValueError(f"registro truncado em {relative}, linha {row_index + 1}")
        payload: dict[str, str | None] = {}
        for field in layout.fields:
            raw_value = raw_record[field.offset : field.offset + field.length]
            payload[field.name] = (
                read_fpt_memo(fpt_path, raw_value) if field.type == "M" else decode_field(raw_value)
            )
        records.append(
            {
                "source_file": relative,
                "source_table": path.stem.upper(),
                "source_row": row_index + 1,
                "record_sha256": hashlib.sha256(raw_record).hexdigest(),
                "deleted_in_source": raw_record[:1] == b"*",
                "payload_json": payload,
                "imported_at": datetime.now(UTC).replace(tzinfo=None),
            }
        )

    after = file_sha256(path)
    if after != before:
        raise RuntimeError(f"arquivo de origem alterado durante leitura: {relative}")
    return ParsedFile(
        path=path,
        source_file=relative,
        source_table=path.stem.upper(),
        records=records,
        sha256_before=before,
        duration_seconds=round(time.perf_counter() - started, 4),
    )


def upsert_batches(engine: Any, records: list[dict[str, Any]], batch_size: int) -> None:
    table = LegacyRawRecord.__table__
    with engine.begin() as connection:
        for offset in range(0, len(records), batch_size):
            statement = mysql_insert(table).values(records[offset : offset + batch_size])
            update = {
                "source_table": statement.inserted.source_table,
                "record_sha256": statement.inserted.record_sha256,
                "deleted_in_source": statement.inserted.deleted_in_source,
                "payload_json": statement.inserted.payload_json,
                "imported_at": statement.inserted.imported_at,
            }
            connection.execute(statement.on_duplicate_key_update(**update))


def run(source: Path, output: Path, workers: int, batch_size: int) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    files = sorted(path for path in source.rglob("*") if path.is_file() and is_dbf_format(path))
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(parse_file, path, source): path for path in files}
        for future in as_completed(pending):
            path = pending[future]
            try:
                parsed = future.result()
                upsert_batches(engine, parsed.records, batch_size)
                results.append(
                    {
                        "source_file": parsed.source_file,
                        "source_table": parsed.source_table,
                        "rows": len(parsed.records),
                        "deleted_rows": sum(r["deleted_in_source"] for r in parsed.records),
                        "sha256": parsed.sha256_before,
                        "read_seconds": parsed.duration_seconds,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {"source_file": path.relative_to(source).as_posix(), "error": str(exc)}
                )

    expected_rows = sum(item["rows"] for item in results)
    with engine.connect() as connection:
        stored_rows = connection.scalar(select(func.count()).select_from(LegacyRawRecord)) or 0
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(source.resolve()),
        "workers": workers,
        "batch_size": batch_size,
        "files_discovered": len(files),
        "files_imported": len(results),
        "expected_rows": expected_rows,
        "stored_rows": stored_rows,
        "errors": errors,
        "tables": sorted(results, key=lambda item: item["source_file"]),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "integrity": "PASS"
        if not errors and len(results) == len(files) and stored_rows == expected_rows
        else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa DBFs legados para staging MySQL")
    parser.add_argument("--source", type=Path, default=Path("ABEL-BAK"))
    parser.add_argument("--output", type=Path, default=Path("docs/fase_4_importacao.json"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    report = run(args.source, args.output, args.workers, args.batch_size)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {"tables"}},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
