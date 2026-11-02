from __future__ import annotations

import getpass

import paramiko

HOST = "192.168.0.15"
PORT = 8022
USER = "u0_a312"

COMMAND = r'''
set -u
echo '--- supervisor ---'
ps -A -o pid,args | grep '[r]unsvdir' || true
echo '--- servicos ABEL ---'
for service in abel-mariadb abel-api; do
  sv status "$PREFIX/var/service/$service" 2>&1 || true
done
echo '--- arquivos ---'
ls -ld "$PREFIX/var/service/abel-mariadb" "$PREFIX/var/service/abel-api" 2>&1 || true
proot-distro login debian -- bash -lc '
  /opt/abel/.venv/bin/python --version 2>&1 || true
  test -f /opt/abel/.env && echo env=present || echo env=missing
  mariadb-admin ping --silent 2>&1 || true
  curl -fsS http://127.0.0.1:8001/abel/api/health 2>&1 || true
'
'''


def main() -> int:
    password = getpass.getpass("Senha SSH: ")
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
        _, stdout, stderr = client.exec_command(COMMAND, timeout=45)
        print(stdout.read().decode("utf-8", errors="replace"), end="")
        error = stderr.read().decode("utf-8", errors="replace")
        if error:
            print(error, end="")
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
