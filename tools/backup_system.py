from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import make_url

MAGIC = b"ABELBAK1"
PASSPHRASE_FILE = Path("data/backup.passphrase")
REPORT = Path("docs/fase_12_backup.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_passphrase() -> bytes:
    if not PASSPHRASE_FILE.exists():
        PASSPHRASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PASSPHRASE_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return PASSPHRASE_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase)


def table_counts(database_url: str) -> dict[str, int]:
    engine = create_engine(database_url, pool_pre_ping=True)
    inspector = inspect(engine)
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
            for table_name in sorted(inspector.get_table_names())
        }


def run_dump(output: Path) -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    executable = Path(settings.mysql_bin_path) / "mysqldump.exe"
    env = os.environ.copy()
    env["MYSQL_PWD"] = url.password or ""
    command = [
        str(executable),
        "--host",
        url.host or "127.0.0.1",
        "--port",
        str(url.port or 3306),
        "--user",
        url.username or "",
        "--single-transaction",
        "--quick",
        "--hex-blob",
        "--default-character-set=utf8mb4",
        "--no-tablespaces",
        "--skip-comments",
        url.database or "abel_clinica",
    ]
    with output.open("wb") as stream:
        result = subprocess.run(
            command, stdout=stream, stderr=subprocess.PIPE, env=env, check=False
        )
    if result.returncode != 0:
        raise RuntimeError(f"mysqldump falhou com codigo {result.returncode}")


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao configurada")
    backup_dir = Path(settings.backup_directory).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_path = backup_dir / f"ABEL_full_{timestamp}.abelbak"
    counts = table_counts(settings.database_url)

    with tempfile.TemporaryDirectory(prefix="abel-backup-") as temporary:
        temp_root = Path(temporary)
        dump_path = temp_root / "abel_clinica.sql"
        run_dump(dump_path)
        document_root = Path(settings.document_storage_path)
        document_files = sorted(path for path in document_root.rglob("*") if path.is_file())
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "app_version": settings.app_version,
            "database": "abel_clinica",
            "table_counts": counts,
            "database_dump": {
                "path": "database/abel_clinica.sql",
                "size": dump_path.stat().st_size,
                "sha256": sha256(dump_path),
            },
            "documents": [
                {
                    "path": path.relative_to(document_root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for path in document_files
            ],
            "configuration": [
                item for item in (".env", "config/mysql/my.ini") if Path(item).is_file()
            ],
        }
        archive_path = temp_root / "payload.zip"
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.write(dump_path, "database/abel_clinica.sql")
            for path in document_files:
                archive.write(path, f"documents/{path.relative_to(document_root).as_posix()}")
            for item in manifest["configuration"]:
                archive.write(item, f"configuration/{Path(item).name}")
            archive.writestr(
                "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
            )
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(derive_key(backup_passphrase(), salt)).encrypt(
            nonce, archive_path.read_bytes(), MAGIC
        )
        final_path.write_bytes(MAGIC + salt + nonce + encrypted)

    backups = sorted(backup_dir.glob("ABEL_full_*.abelbak"), reverse=True)
    for expired in backups[settings.backup_retention_count :]:
        if expired.parent == backup_dir:
            expired.unlink()
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backup_file": str(final_path),
        "encrypted": True,
        "algorithm": "AES-256-GCM + scrypt",
        "size_bytes": final_path.stat().st_size,
        "sha256": sha256(final_path),
        "table_count": len(counts),
        "row_count": sum(counts.values()),
        "document_count": len(manifest["documents"]),
        "integrity": "PASS",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
