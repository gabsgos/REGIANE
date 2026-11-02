import json
import logging

from backend.app.core.logging_config import JsonFormatter


def test_json_log_contains_only_operational_context() -> None:
    record = logging.LogRecord("abel", logging.INFO, __file__, 1, "request_completed", (), None)
    record.request_id = "abc"
    record.method = "GET"
    record.path = "/api/health"
    record.status_code = 200
    record.duration_ms = 1.5
    content = json.loads(JsonFormatter().format(record))
    assert content["message"] == "request_completed"
    assert content["path"] == "/api/health"
    assert "query" not in content
    assert "body" not in content
    assert "headers" not in content
