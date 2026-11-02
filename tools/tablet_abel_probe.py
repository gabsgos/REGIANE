# ruff: noqa: E501

from __future__ import annotations

import json
import getpass
import sys

import paramiko

HOST = "192.168.0.15"
PORT = 8022
USER = "u0_a312"

TERMUX_COMMAND = r"""
set -eu
echo '---TERMUX---'
uname -a
df -h "$HOME" | tail -n 1
command -v proot-distro || true
ROOT="$PREFIX/var/lib/proot-distro/installed-rootfs/debian"
du -sh "$ROOT/opt/fisia" 2>/dev/null || true
readlink -f "$ROOT/opt/fisia" 2>/dev/null || true
du -sh "$HOME"/* 2>/dev/null | sort -h | tail -n 12
ps -A -o pid,args | grep '[p]root' | head -n 8 || true
echo '---BACKUPS---'
find "$HOME" -maxdepth 2 -type f \( -name '*backup*.tar*' -o -name 'fisia_full_*.tar*' \) -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\n' 2>/dev/null | sort -r | head -n 8
echo '---SERVICES---'
for service in sshd fisia-web-static fisia-reverse-proxy fisia-supervisor; do sv status "$PREFIX/var/service/$service" 2>&1 || true; done
echo '---DEBIAN---'
proot-distro login debian -- bash -lc '
set -eu
uname -m
cat /etc/os-release | grep -E "^(PRETTY_NAME|VERSION_ID)="
df -h /opt | tail -n 1
free -h | head -n 2
for tool in python3 poetry pip3 mysql mariadb sqlite3; do printf "%s=" "$tool"; command -v "$tool" || true; done
python3 --version 2>&1 || true
poetry --version 2>&1 || true
mysql --version 2>&1 || mariadb --version 2>&1 || true
sqlite3 --version 2>&1 || true
ss -ltn 2>/dev/null | grep -E ":(8000|8001|8080|3306|5432) " || true
test -d /opt/fisia && echo fisia_runtime=present || echo fisia_runtime=missing
test -d /opt/abel && echo abel_runtime=present || echo abel_runtime=missing
du -sh /opt/fisia 2>/dev/null || true
find /opt/fisia -type f 2>/dev/null | wc -l
ls -ld /opt/fisia
df -h /opt/fisia | tail -n 1
grep -F '/opt/fisia' /proc/self/mountinfo 2>/dev/null || true
ps -eo pid,ppid,stat,etime,args | grep -E '(poetry|pip|uvicorn|mariadb)' | tail -n 20 || true
dpkg-query -W python3 python3-venv python3-dev build-essential default-libmysqlclient-dev mariadb-server sqlite3 2>/dev/null || true
'
"""


def main() -> int:
    password = getpass.getpass("Senha SSH: ")
    if not password:
        raise RuntimeError("Senha SSH nao fornecida por stdin")
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
        _, stdout, stderr = client.exec_command(TERMUX_COMMAND, timeout=45)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
    finally:
        client.close()
    print(output, end="")
    if error:
        print(json.dumps({"stderr": error}, ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
