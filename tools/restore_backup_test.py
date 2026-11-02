from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pymysql
from backend.app.core.config import get_settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from tools.backup_system import MAGIC, PASSPHRASE_FILE, derive_key

REPORT = Path("docs/fase_12_restauracao.json")
ROOT_SECRET = Path("data/mysql-root.secret")
RESTORE_DATABASE = "abel_restore_test"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    target_resolved = target.resolve()
    for member in archive.infolist():
        destination = (target / member.filename).resolve()
        if target_resolved not in destination.parents and destination != target_resolved:
            raise RuntimeError("caminho inseguro no backup")
    archive.extractall(target)


def mysql_command(sql_file: Path, database: str) -> None:
    settings = get_settings()
    executable = Path(settings.mysql_bin_path) / "mysql.exe"
    env = os.environ.copy()
    env["MYSQL_PWD"] = ROOT_SECRET.read_text(encoding="utf-8").strip()
    command = [
        str(executable),
        "--host",
        "127.0.0.1",
        "--port",
        "3307",
        "--user",
        "root",
        "--default-character-set=utf8mb4",
        database,
    ]
    with sql_file.open("rb") as stream:
        result = subprocess.run(command, stdin=stream, stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"restauracao mysql falhou com codigo {result.returncode}")


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


def main() -> int:
    settings = get_settings()
    if not re.fullmatch(r"abel_restore_test", RESTORE_DATABASE):
        raise RuntimeError("nome do banco de teste invalido")
    backups = sorted(Path(settings.backup_directory).resolve().glob("ABEL_full_*.abelbak"))
    if not backups:
        raise RuntimeError("backup criptografado nao encontrado")
    backup = backups[-1]
    raw = backup.read_bytes()
    if not raw.startswith(MAGIC):
        raise RuntimeError("cabecalho do backup invalido")
    salt = raw[len(MAGIC) : len(MAGIC) + 16]
    nonce = raw[len(MAGIC) + 16 : len(MAGIC) + 28]
    ciphertext = raw[len(MAGIC) + 28 :]
    passphrase = PASSPHRASE_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
    payload = AESGCM(derive_key(passphrase, salt)).decrypt(nonce, ciphertext, MAGIC)

    with tempfile.TemporaryDirectory(prefix="abel-restore-") as temporary:
        temp_root = Path(temporary)
        zip_path = temp_root / "payload.zip"
        zip_path.write_bytes(payload)
        extract_root = temp_root / "extracted"
        with zipfile.ZipFile(zip_path) as archive:
            safe_extract(archive, extract_root)
        manifest = json.loads((extract_root / "manifest.json").read_text(encoding="utf-8"))
        dump_path = extract_root / manifest["database_dump"]["path"]
        dump_hash_ok = sha256(dump_path) == manifest["database_dump"]["sha256"]

        with root_connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{RESTORE_DATABASE}`")
            cursor.execute(
                f"CREATE DATABASE `{RESTORE_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        mysql_command(dump_path, RESTORE_DATABASE)
        actual_counts: dict[str, int] = {}
        with root_connection(RESTORE_DATABASE) as connection, connection.cursor() as cursor:
            for table in manifest["table_counts"]:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                actual_counts[table] = int(cursor.fetchone()[0])
        table_counts_ok = actual_counts == manifest["table_counts"]
        document_hashes_ok = all(
            sha256(extract_root / "documents" / item["path"]) == item["sha256"]
            for item in manifest["documents"]
        )
        with root_connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{RESTORE_DATABASE}`")

    criteria = {
        "aes_gcm_authentication": True,
        "dump_hash": dump_hash_ok,
        "all_table_counts": table_counts_ok,
        "all_document_hashes": document_hashes_ok,
        "isolated_database_removed": True,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backup_file": str(backup),
        "restored_table_count": len(actual_counts),
        "restored_row_count": sum(actual_counts.values()),
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
