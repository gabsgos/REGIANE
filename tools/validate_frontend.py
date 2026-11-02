from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from backend.app.main import create_app
from fastapi.testclient import TestClient

OUTPUT = Path("docs/fase_10_validacao_frontend.json")


def main() -> int:
    client = TestClient(create_app())
    index = client.get("/abel.html")
    css = client.get("/abel/assets/css/app.css")
    visibility_css = client.get("/abel/assets/css/visibility.css")
    app_js = client.get("/abel/assets/js/app.js")
    api_js = client.get("/abel/assets/js/api.js")
    sources = "\n".join((index.text, css.text, visibility_css.text, app_js.text, api_js.text))
    node_results = [
        subprocess.run(
            ["node", "--check", path], capture_output=True, text=True, check=False
        ).returncode
        for path in ("frontend/js/api.js", "frontend/js/app.js")
    ]
    required_paths = [
        'api("/auth/login"',
        'api("/auth/me"',
        'api("/patients"',
        'api("/appointments"',
        'api("/finance/payments"',
        "/documents/appointments/",
        'api("/admin/users"',
        "/reports/appointments",
    ]
    criteria = {
        "index_served": index.status_code == 200,
        "assets_served": all(
            item.status_code == 200 for item in (css, visibility_css, app_js, api_js)
        ),
        "javascript_syntax": node_results == [0, 0],
        "api_flows_connected": all(path in sources for path in required_paths),
        "no_inner_html": "innerHTML" not in sources,
        "no_mock_login": "perfil-simulado" not in sources and "123456" not in sources,
        "no_local_storage_auth": "localStorage" not in sources,
        "responsive_tablet_css": "@media(max-width:820px)" in css.text,
        "role_visibility": "data-roles" in index.text and "applyPermissions" in app_js.text,
        "loading_and_errors": "appointments-loading" in index.text and "showToast" in app_js.text,
        "hidden_views_are_not_rendered": "display: none !important" in visibility_css.text,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
