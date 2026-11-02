# ruff: noqa: E501

from __future__ import annotations

import base64
import getpass
import secrets
import shlex
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import paramiko

HOST = "192.168.0.15"
PORT = 8022
USER = "u0_a312"
PAYLOAD = Path(r"C:\Users\gabri\AppData\Local\Temp\abel-tablet-build55-20261102-1806.tar.gz")
PROXY = Path(r"C:\Users\gabri\Documents\FisioBot\reverse_proxy.py")
BUILD = Path(r"C:\Users\gabri\Documents\FisioBot\BUILD.txt")
REMOTE_STAGE = "/data/data/com.termux/files/home/codex_tmp"


def encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def run(client: paramiko.SSHClient, label: str, command: str, timeout: int = 900) -> None:
    print(f"--- {label} ---", flush=True)
    _, stdout, _ = client.exec_command(command, timeout=timeout, get_pty=True)
    for line in iter(stdout.readline, ""):
        print(line.rstrip(), flush=True)
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"Etapa {label} falhou com status {status}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    password = getpass.getpass("Senha SSH: ")
    if not password:
        raise RuntimeError("Senha SSH nao fornecida por stdin")
    if not all(path.is_file() for path in (PAYLOAD, PROXY, BUILD)):
        raise RuntimeError("Artefato local de deploy ausente")
    database_password = secrets.token_urlsafe(24)
    database_url = (
        "mysql+pymysql://abel_app:"
        f"{quote(database_password, safe='')}@127.0.0.1:3306/abel_clinica?charset=utf8mb4"
    )
    env_file = "\n".join(
        (
            "ABEL_ENVIRONMENT=production",
            f"ABEL_DATABASE_URL={database_url}",
            "ABEL_API_HOST=127.0.0.1",
            "ABEL_API_PORT=8001",
            "ABEL_COOKIE_SECURE=true",
            "ABEL_AUTHORIZATION_MODE=ENFORCE",
            "ABEL_AUTHORIZATION_ADMIN_MODE=ENFORCE",
            "ABEL_AUTHORIZATION_FINANCE_MODE=ENFORCE",
            "ABEL_AUTHORIZATION_CLINICAL_MODE=ENFORCE",
            "ABEL_AUTHORIZATION_DOCUMENTS_MODE=ENFORCE",
            "ABEL_AUTHORIZATION_REPORTS_MODE=ENFORCE",
            "ABEL_DOCUMENT_STORAGE_PATH=/opt/abel/data/documents",
            "ABEL_LOG_PATH=/opt/abel/data/logs/abel.jsonl",
            "ABEL_BACKUP_DIRECTORY=/opt/abel/backups/system",
            "ABEL_MYSQL_BIN_PATH=/usr/bin",
            "ABEL_STEP_UP_MINUTES=15",
            "",
        )
    )
    mariadb_run = """#!/data/data/com.termux/files/usr/bin/sh
exec proot-distro login debian -- bash -lc 'mkdir -p /run/mysqld; chown mysql:mysql /run/mysqld; exec /usr/sbin/mariadbd --user=mysql --bind-address=127.0.0.1 --port=3306'
"""
    mariadb_maintenance_run = """#!/data/data/com.termux/files/usr/bin/sh
exec proot-distro login debian -- bash -lc 'mkdir -p /run/mysqld; chown mysql:mysql /run/mysqld; exec /usr/sbin/mariadbd --user=mysql --skip-grant-tables --bind-address=127.0.0.1 --port=3306'
"""
    api_run = """#!/data/data/com.termux/files/usr/bin/sh
exec proot-distro login debian -- bash -lc 'cd /opt/abel; exec /opt/abel/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8001'
"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=12,
    )
    try:
        run(client, "staging", f"mkdir -p {REMOTE_STAGE}")
        with client.open_sftp() as sftp:
            sftp.put(str(PAYLOAD), f"{REMOTE_STAGE}/abel-build55.tar.gz")
            sftp.put(str(PROXY), f"{REMOTE_STAGE}/reverse_proxy.py")
            sftp.put(str(BUILD), f"{REMOTE_STAGE}/BUILD.txt")
        run(
            client,
            "dependencias",
            "proot-distro login debian -- bash -lc "
            + shlex.quote(
                "export DEBIAN_FRONTEND=noninteractive; "
                "apt-get update; apt-get install -y mariadb-server mariadb-client "
                "python3-venv python3-dev build-essential curl"
            ),
        )
        setup = f"""
set -eu
proot-distro login debian -- bash -lc {shlex.quote(
    'mkdir -p /opt/abel /opt/abel/data/documents /opt/abel/data/logs; '
    f'tar -xzf {REMOTE_STAGE}/abel-build55.tar.gz -C /opt/abel; '
    'rm -rf /opt/abel-poetry /opt/abel/.venv; '
    '/usr/bin/python3 -m venv /opt/abel-poetry; '
    '/opt/abel-poetry/bin/pip install --upgrade pip; '
    '/opt/abel-poetry/bin/pip install poetry==2.3.4; '
    'cd /opt/abel; /opt/abel-poetry/bin/poetry config virtualenvs.in-project true; '
    'POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON=true '
    '/opt/abel-poetry/bin/poetry env use /usr/bin/python3; '
    '/opt/abel-poetry/bin/poetry install --only main --no-root --no-interaction --no-ansi'
)}
printf %s {shlex.quote(encode(env_file))} | base64 -d | \
  proot-distro login debian -- bash -lc 'cat > /opt/abel/.env && chmod 600 /opt/abel/.env'
mkdir -p "$PREFIX/var/service/abel-mariadb" "$PREFIX/var/service/abel-api"
printf %s {shlex.quote(encode(mariadb_run))} | base64 -d > "$PREFIX/var/service/abel-mariadb/run"
printf %s {shlex.quote(encode(api_run))} | base64 -d > "$PREFIX/var/service/abel-api/run"
chmod 755 "$PREFIX/var/service/abel-mariadb/run" "$PREFIX/var/service/abel-api/run"
sv up "$PREFIX/var/service/abel-mariadb"
for i in $(seq 1 60); do
  proot-distro login debian -- mariadb-admin ping --silent && break
  sleep 1
done
proot-distro login debian -- mariadb-admin ping --silent
"""
        run(client, "runtime", setup)
        database_sql = (
            "CREATE DATABASE IF NOT EXISTS abel_clinica "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
            "CREATE USER IF NOT EXISTS 'abel_app'@'127.0.0.1' IDENTIFIED BY "
            f"'{database_password}'; "
            "ALTER USER 'abel_app'@'127.0.0.1' IDENTIFIED BY "
            f"'{database_password}'; "
            "GRANT ALL PRIVILEGES ON abel_clinica.* TO 'abel_app'@'127.0.0.1'; "
            "FLUSH PRIVILEGES;"
        )
        database = f"""
set -eu
sv force-stop "$PREFIX/var/service/abel-mariadb" || true
proot-distro login debian -- pkill -KILL -x mariadbd 2>/dev/null || true
sleep 2
sv force-stop "$PREFIX/var/service/abel-mariadb" || true
printf %s {shlex.quote(encode(mariadb_maintenance_run))} | base64 -d > "$PREFIX/var/service/abel-mariadb/run"
chmod 755 "$PREFIX/var/service/abel-mariadb/run"
sv start "$PREFIX/var/service/abel-mariadb"
for i in $(seq 1 60); do
  proot-distro login debian -- mariadb-admin ping --silent && break
  sleep 1
done
proot-distro login debian -- mariadb -uroot -e {shlex.quote('FLUSH PRIVILEGES; ' + database_sql)}
sv force-stop "$PREFIX/var/service/abel-mariadb" || true
proot-distro login debian -- pkill -KILL -x mariadbd 2>/dev/null || true
sleep 2
sv force-stop "$PREFIX/var/service/abel-mariadb" || true
printf %s {shlex.quote(encode(mariadb_run))} | base64 -d > "$PREFIX/var/service/abel-mariadb/run"
chmod 755 "$PREFIX/var/service/abel-mariadb/run"
sv start "$PREFIX/var/service/abel-mariadb"
for i in $(seq 1 60); do
  proot-distro login debian -- mariadb-admin ping --silent && break
  sleep 1
done
proot-distro login debian -- bash -lc {shlex.quote(
    f'MYSQL_PWD={shlex.quote(database_password)} mariadb -h127.0.0.1 -uabel_app abel_clinica < /opt/abel/abel_clinica.sql'
)}
proot-distro login debian -- bash -lc {shlex.quote(
    f'MYSQL_PWD={shlex.quote(database_password)} mariadb -h127.0.0.1 -uabel_app -N abel_clinica -e "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM patients;"'
)}
sv restart "$PREFIX/var/service/abel-api"
for i in $(seq 1 60); do
  proot-distro login debian -- curl -fsS http://127.0.0.1:8001/abel/api/health && break
  sleep 1
done
proot-distro login debian -- curl -fsS http://127.0.0.1:8001/abel/api/health
"""
        run(client, "banco-e-api", database)
        proxy = f"""
set -eu
ROLLBACK=/opt/fisia/runtime/deploy_backups/pre_abel_build55_{stamp}
proot-distro login debian -- mkdir -p "$ROLLBACK"
proot-distro login debian -- cp /opt/fisia/reverse_proxy.py "$ROLLBACK/reverse_proxy.py"
proot-distro login debian -- cp /opt/fisia/BUILD.txt "$ROLLBACK/BUILD.txt"
proot-distro login debian -- cp {REMOTE_STAGE}/reverse_proxy.py /opt/fisia/reverse_proxy.py
proot-distro login debian -- cp {REMOTE_STAGE}/BUILD.txt /opt/fisia/BUILD.txt
sv restart "$PREFIX/var/service/fisia-reverse-proxy"
sleep 3
curl -fsS http://127.0.0.1:8080/abel/api/health
curl -fsS http://127.0.0.1:8080/abel.html >/dev/null
printf 'rollback=%s\n' "$ROLLBACK"
sv status "$PREFIX/var/service/abel-mariadb"
sv status "$PREFIX/var/service/abel-api"
sv status "$PREFIX/var/service/fisia-reverse-proxy"
"""
        run(client, "proxy-e-servicos", proxy)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
