from __future__ import annotations

import json
from pathlib import Path

import requests

BASE_URL = "https://walk-gaming-magazine.ngrok-free.dev/abel/api"
HEADERS = {"ngrok-skip-browser-warning": "true"}


def read_secret(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def validate(name: str, secret_path: Path, checks: dict[str, int]) -> dict[str, object]:
    secret = read_secret(secret_path)
    with requests.Session() as client:
        client.headers.update(HEADERS)
        login = client.post(
            f"{BASE_URL}/auth/login",
            json={"username": secret["username"], "password": secret["password"]},
            timeout=30,
        )
        result: dict[str, object] = {
            "account": name,
            "username": secret["username"],
            "login": login.status_code,
        }
        if login.status_code != 200:
            return result
        me = client.get(f"{BASE_URL}/auth/me", timeout=30)
        result["me"] = me.status_code
        result["role"] = me.json().get("role") if me.status_code == 200 else None
        for path, expected in checks.items():
            status = client.get(f"{BASE_URL}{path}", timeout=30).status_code
            result[path] = {"status": status, "expected": expected, "pass": status == expected}
        return result


def main() -> int:
    results = [
        validate(
            "leandro",
            Path("data/leandro-manager.secret"),
            {"/admin/users": 200, "/finance/summary": 200},
        ),
        validate(
            "gabriel",
            Path("data/homologation-doctor.secret"),
            {"/clinical/worklist": 200, "/finance/summary": 403},
        ),
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    passed = all(
        result.get("login") == 200
        and result.get("me") == 200
        and all(
            value.get("pass") is True
            for key, value in result.items()
            if key.startswith("/") and isinstance(value, dict)
        )
        for result in results
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
