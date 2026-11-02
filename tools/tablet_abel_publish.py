from __future__ import annotations

import getpass
from datetime import datetime
from pathlib import Path

import paramiko

HOST = "192.168.0.15"
PORT = 8022
USER = "u0_a312"
PROXY = Path(r"C:\Users\gabri\Documents\FisioBot\reverse_proxy.py")
BUILD = Path(r"C:\Users\gabri\Documents\FisioBot\BUILD.txt")
REMOTE_STAGE = "/data/data/com.termux/files/home/codex_tmp"


def main() -> int:
    password = getpass.getpass("Senha SSH: ")
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
        with client.open_sftp() as sftp:
            sftp.put(str(PROXY), f"{REMOTE_STAGE}/reverse_proxy.py")
            sftp.put(str(BUILD), f"{REMOTE_STAGE}/BUILD.txt")
        command = f'''
set -eu
sv -w 2 down "$PREFIX/var/service/abel-api" || true
sv -w 2 kill "$PREFIX/var/service/abel-api" || true
sleep 2
sv -w 2 down "$PREFIX/var/service/abel-api" || true
sv start "$PREFIX/var/service/abel-api"
for i in $(seq 1 60); do
  proot-distro login debian -- curl -fsS http://127.0.0.1:8001/abel/api/health && break
  sleep 1
done
proot-distro login debian -- curl -fsS http://127.0.0.1:8001/abel/api/health
ROLLBACK=/opt/fisia/runtime/deploy_backups/pre_abel_build55_{stamp}
proot-distro login debian -- mkdir -p "$ROLLBACK"
proot-distro login debian -- cp /opt/fisia/reverse_proxy.py "$ROLLBACK/reverse_proxy.py"
proot-distro login debian -- cp /opt/fisia/BUILD.txt "$ROLLBACK/BUILD.txt"
proot-distro login debian -- cp {REMOTE_STAGE}/reverse_proxy.py /opt/fisia/reverse_proxy.py
proot-distro login debian -- cp {REMOTE_STAGE}/BUILD.txt /opt/fisia/BUILD.txt
sv -w 2 down "$PREFIX/var/service/fisia-reverse-proxy" || true
sv -w 2 kill "$PREFIX/var/service/fisia-reverse-proxy" || true
sleep 2
sv -w 2 down "$PREFIX/var/service/fisia-reverse-proxy" || true
sv start "$PREFIX/var/service/fisia-reverse-proxy"
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8080/abel/api/health && break
  sleep 1
done
curl -fsS http://127.0.0.1:8080/abel/api/health
curl -fsS http://127.0.0.1:8080/abel.html >/dev/null
printf 'rollback=%s\n' "$ROLLBACK"
sv status "$PREFIX/var/service/abel-mariadb"
sv status "$PREFIX/var/service/abel-api"
sv status "$PREFIX/var/service/fisia-reverse-proxy"
'''
        _, stdout, stderr = client.exec_command(command, timeout=240, get_pty=True)
        for line in iter(stdout.readline, ""):
            print(line.rstrip(), flush=True)
        error = stderr.read().decode("utf-8", errors="replace")
        if error:
            print(error, end="")
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
