from pathlib import Path

from tools.import_legacy import parse_file, read_fpt_memo

from tests.test_legacy_inventory import create_minimal_dbf


def test_parse_file_preserves_source_and_payload(tmp_path: Path) -> None:
    path = tmp_path / "TESTE.DBF"
    create_minimal_dbf(path)

    parsed = parse_file(path, tmp_path)

    assert parsed.source_file == "TESTE.DBF"
    assert parsed.source_table == "TESTE"
    assert parsed.records[0]["source_row"] == 1
    assert parsed.records[0]["payload_json"] == {"NOME": "TESTE"}
    assert parsed.records[0]["deleted_in_source"] is False
    assert len(parsed.records[0]["record_sha256"]) == 64


def test_missing_fpt_returns_none(tmp_path: Path) -> None:
    assert read_fpt_memo(tmp_path / "missing.fpt", b"         1") is None
