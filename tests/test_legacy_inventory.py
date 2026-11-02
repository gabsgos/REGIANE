import struct
from pathlib import Path

from tools.legacy_inventory import active_records, is_dbf_format, parse_layout


def create_minimal_dbf(path: Path) -> None:
    field = bytearray(32)
    field[:5] = b"NOME\0"
    field[11] = ord("C")
    field[16] = 10
    header_length = 32 + 32 + 1
    record_length = 11
    header = bytearray(32)
    header[0] = 0x03
    header[1:4] = bytes((126, 10, 31))
    header[4:8] = struct.pack("<I", 1)
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)
    path.write_bytes(bytes(header) + bytes(field) + b"\r" + b" TESTE     " + b"\x1a")


def test_parse_layout_and_active_record(tmp_path: Path) -> None:
    path = tmp_path / "TESTE.DBF"
    create_minimal_dbf(path)

    layout = parse_layout(path)

    assert layout.declared_rows == 1
    assert layout.record_length == 11
    assert layout.fields[0].name == "NOME"
    assert len(active_records(layout)) == 1
    assert is_dbf_format(path) is True


def test_rejects_non_dbf(tmp_path: Path) -> None:
    path = tmp_path / "texto.txt"
    path.write_text("nao e dbf", encoding="utf-8")

    assert is_dbf_format(path) is False
