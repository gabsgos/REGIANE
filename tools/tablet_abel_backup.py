from __future__ import annotations

import json
import sys
from datetime import datetime

import paramiko

HOST = "192.168.0.15"
PORT = 8022
USER = "u0_a312"


def main() -> int:
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise RuntimeError("Senha SSH nao fornecida por stdin")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"fisia_full_pre_abel_build55_{stamp}.tar"
    remote = f"/data/data/com.termux/files/home/backups/{name}"
    command = f"""
set -eu
ROOT="$PREFIX/var/lib/proot-distro/containers/debian/rootfs"
BACKUP={remote!r}
mkdir -p "$HOME/backups"
test -d "$ROOT/opt/fisia"
tar -cf "$BACKUP" \
  -C "$ROOT" opt/fisia \
  -C "$PREFIX/var" service \
  -C "$HOME" .fisia 2>/dev/null || \
tar -cf "$BACKUP" -C "$ROOT" opt/fisia -C "$PREFIX/var" service
tar -tf "$BACKUP" > "$BACKUP.contents"
sha256sum "$BACKUP" > "$BACKUP.sha256"
sha256sum -c "$BACKUP.sha256"
test "$(stat -c %s "$BACKUP")" -gt 100000000
grep -q '^opt/fisia/' "$BACKUP.contents"
grep -q '^service/' "$BACKUP.contents"
printf 'backup=%s\n' "$BACKUP"
stat -c 'size=%s modified=%y' "$BACKUP"
printf 'entries=%s\n' "$(wc -l < "$BACKUP.contents")"
cat "$BACKUP.sha256"
"""
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
        _, stdout, stderr = client.exec_command(command, timeout=300)
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
