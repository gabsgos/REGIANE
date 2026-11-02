from __future__ import annotations

import argparse
import os
from pathlib import Path

import paramiko


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.getenv("TABLET_SSH_HOST", "192.168.0.15"),
        port=int(os.getenv("TABLET_SSH_PORT", "8022")),
        username=os.getenv("TABLET_SSH_USERNAME", "u0_a312"),
        password=os.environ["TABLET_SSH_PASSWORD"],
        timeout=15,
    )
    return client


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command")
    group.add_argument("--upload", nargs=2, metavar=("LOCAL", "REMOTE"))
    args = parser.parse_args()
    with connect() as client:
        if args.command:
            _, stdout, stderr = client.exec_command(args.command, timeout=1800)
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            if output:
                print(output, end="")
            if error:
                print(error, end="")
            return exit_code
        local, remote = args.upload
        with client.open_sftp() as sftp:
            sftp.put(str(Path(local).resolve()), remote)
        print(remote)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
