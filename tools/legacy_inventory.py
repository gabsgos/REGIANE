from __future__ import annotations

import argparse
import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DBF_VERSIONS = {0x02, 0x03, 0x04, 0x05, 0x30, 0x31, 0x32, 0x43, 0x63, 0x83, 0x8B, 0xCB, 0xF5, 0xFB}
CURRENT_YEAR = 2026


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    length: int
    decimals: int
    offset: int


@dataclass(frozen=True)
class Layout:
    path: Path
    version: int
    header_date_raw: str
    declared_rows: int
    header_length: int
    record_length: int
    fields: tuple[Field, ...]


def parse_layout(path: Path) -> Layout:
    data = path.read_bytes()
    if len(data) < 33 or data[0] not in DBF_VERSIONS:
        raise ValueError(f"Arquivo nao reconhecido como DBF: {path}")

    declared_rows = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    if header_length < 33 or header_length > len(data) or record_length < 1:
        raise ValueError(f"Cabecalho DBF invalido: {path}")
    expected_data_end = header_length + declared_rows * record_length
    if expected_data_end > len(data) + 1:
        raise ValueError(f"Quantidade de registros incoerente com o arquivo: {path}")

    fields: list[Field] = []
    descriptor_offset = 32
    record_offset = 1
    while descriptor_offset < header_length and data[descriptor_offset] != 0x0D:
        descriptor = data[descriptor_offset : descriptor_offset + 32]
        if len(descriptor) != 32:
            raise ValueError(f"Descritor DBF truncado: {path}")
        raw_name = descriptor[:11].split(b"\0", 1)[0]
        if not raw_name or any(byte < 32 or byte > 126 for byte in raw_name):
            raise ValueError(f"Campo DBF sem nome: {path}")
        field_length = descriptor[16]
        field_type = chr(descriptor[11])
        if field_type not in {"C", "N", "F", "D", "L", "M", "I", "B", "Y", "T"}:
            raise ValueError(f"Tipo de campo DBF invalido: {path}")
        if field_length < 1:
            raise ValueError(f"Tamanho de campo DBF invalido: {path}")
        fields.append(
            Field(
                name=raw_name.decode("ascii", "replace").upper(),
                type=field_type,
                length=field_length,
                decimals=descriptor[17],
                offset=record_offset,
            )
        )
        record_offset += field_length
        descriptor_offset += 32

    if descriptor_offset >= header_length or data[descriptor_offset] != 0x0D:
        raise ValueError(f"Terminador de campos DBF ausente: {path}")
    if record_offset != record_length:
        raise ValueError(f"Comprimento de registro DBF incoerente: {path}")

    raw_year, raw_month, raw_day = data[1], data[2], data[3]
    return Layout(
        path=path,
        version=data[0],
        header_date_raw=f"{raw_year:03d}-{raw_month:02d}-{raw_day:02d}",
        declared_rows=declared_rows,
        header_length=header_length,
        record_length=record_length,
        fields=tuple(fields),
    )


def is_dbf_format(path: Path) -> bool:
    try:
        parse_layout(path)
    except (OSError, ValueError):
        return False
    return True


def active_records(layout: Layout) -> list[bytes]:
    data = layout.path.read_bytes()
    records: list[bytes] = []
    for index in range(layout.declared_rows):
        start = layout.header_length + index * layout.record_length
        record = data[start : start + layout.record_length]
        if len(record) != layout.record_length:
            break
        if record[:1] != b"*":
            records.append(record)
    return records


def decode_value(record: bytes, field: Field) -> str:
    raw = record[field.offset : field.offset + field.length]
    return raw.decode("cp1252", "replace").strip()


def layout_document(layout: Layout, root: Path) -> dict[str, Any]:
    return {
        "arquivo": layout.path.relative_to(root).as_posix(),
        "extensao": layout.path.suffix,
        "versao_dbf": hex(layout.version),
        "data_cabecalho_raw": layout.header_date_raw,
        "registros_declarados": layout.declared_rows,
        "tamanho_cabecalho": layout.header_length,
        "tamanho_registro": layout.record_length,
        "campos": [asdict(field) for field in layout.fields],
    }


def profile_table(path: Path, root: Path) -> dict[str, Any]:
    layout = parse_layout(path)
    records = active_records(layout)
    physical_rows = max(0, (path.stat().st_size - layout.header_length) // layout.record_length)
    nonblank = {field.name: 0 for field in layout.fields}
    invalid_dates = 0
    implausible_dates = 0
    invalid_numerics = 0
    invalid_dates_by_field: dict[str, int] = {}
    implausible_dates_by_field: dict[str, int] = {}
    invalid_numerics_by_field: dict[str, int] = {}

    for record in records:
        for field in layout.fields:
            value = decode_value(record, field)
            if value:
                nonblank[field.name] += 1
            if field.type == "D" and value:
                try:
                    parsed = datetime.strptime(value, "%Y%m%d")
                    if parsed.year < 1900 or parsed.year > CURRENT_YEAR + 1:
                        implausible_dates += 1
                        implausible_dates_by_field[field.name] = (
                            implausible_dates_by_field.get(field.name, 0) + 1
                        )
                except ValueError:
                    invalid_dates += 1
                    invalid_dates_by_field[field.name] = (
                        invalid_dates_by_field.get(field.name, 0) + 1
                    )
            elif field.type in {"N", "F"} and value:
                try:
                    float(value.replace(",", "."))
                except ValueError:
                    invalid_numerics += 1
                    invalid_numerics_by_field[field.name] = (
                        invalid_numerics_by_field.get(field.name, 0) + 1
                    )

    return {
        "arquivo": path.relative_to(root).as_posix(),
        "registros_declarados": layout.declared_rows,
        "registros_fisicos": physical_rows,
        "registros_ativos": len(records),
        "registros_duplicados_exatos": len(records) - len(set(records)),
        "datas_invalidas": invalid_dates,
        "datas_formalmente_validas_mas_implausiveis": implausible_dates,
        "numericos_invalidos": invalid_numerics,
        "datas_invalidas_por_campo": invalid_dates_by_field,
        "datas_implausiveis_por_campo": implausible_dates_by_field,
        "numericos_invalidos_por_campo": invalid_numerics_by_field,
        "preenchimento": {
            name: {
                "preenchidos": count,
                "vazios": len(records) - count,
                "percentual_preenchido": round((count / len(records) * 100), 4) if records else 0.0,
            }
            for name, count in nonblank.items()
        },
    }


def load_columns(path: Path, columns: set[str]) -> list[dict[str, str]]:
    layout = parse_layout(path)
    selected = [field for field in layout.fields if field.name in columns]
    return [
        {field.name: decode_value(record, field) for field in selected}
        for record in active_records(layout)
    ]


def normalize_key(value: str) -> str:
    stripped = value.strip()
    return stripped.lstrip("0") or ("0" if stripped else "")


def relationship_profile(root: Path) -> dict[str, Any]:
    relations = [
        ("PAGTOS.DBF", "ALUNO", "CANDIDAT.DBF", "CODIGO"),
        ("DEPOS.DBF", "ALUNO", "CANDIDAT.DBF", "CODIGO"),
        ("L_CARTAO.DBF", "ALUNO", "CANDIDAT.DBF", "CODIGO"),
        ("PROGCART.DBF", "ALUNO", "CANDIDAT.DBF", "CODIGO"),
        ("TMP_ASS.DBF", "ALUNO", "CANDIDAT.DBF", "CODIGO"),
        ("PAGTOS.DBF", "EVENTO", "EVENTOS.DBF", "CODIGO"),
        ("LANCTO.DBF", "CONTA", "CONTBAN.DBF", "CONTA"),
        ("SALDOBAN.DBF", "CONTA", "CONTBAN.DBF", "CONTA"),
        ("CANDIDAT.DBF", "ORIGEM", "ORIGEM.DBF", "CODIGO"),
        ("CANDIDAT.DBF", "COD_NAT", "MUNIC.DBF", "CODIGO"),
    ]
    results: list[dict[str, Any]] = []
    for child_table, child_column, parent_table, parent_column in relations:
        child_rows = load_columns(root / child_table, {child_column})
        parent_rows = load_columns(root / parent_table, {parent_column})
        parent_keys = {
            normalize_key(row[parent_column])
            for row in parent_rows
            if normalize_key(row[parent_column])
        }
        child_keys = [
            normalize_key(row[child_column])
            for row in child_rows
            if normalize_key(row[child_column])
        ]
        unmatched = [key for key in child_keys if key not in parent_keys]
        results.append(
            {
                "filho": f"{child_table}.{child_column}",
                "pai": f"{parent_table}.{parent_column}",
                "linhas_filhas_preenchidas": len(child_keys),
                "linhas_correspondentes": len(child_keys) - len(unmatched),
                "linhas_orfas": len(unmatched),
                "chaves_orfas_distintas": len(set(unmatched)),
            }
        )
    return {"relacionamentos_inferidos": results}


def key_profile(root: Path) -> list[dict[str, Any]]:
    candidates = {
        "CANDIDAT.DBF": ["CODIGO", "CPF", "RENACH", "NRO_PGU"],
        "USUARIOS.DBF": ["COD_USER", "NOME", "CPF"],
        "DR_MED.DBF": ["CRM", "CPF", "CREDENC"],
        "RECIBO.DBF": ["NRO_RECIBO"],
        "MUNIC.DBF": ["CODIGO", "COD_SEQ"],
        "EVENTOS.DBF": ["CODIGO"],
        "CONTBAN.DBF": ["CONTA"],
        "ORIGEM.DBF": ["CODIGO"],
    }
    result: list[dict[str, Any]] = []
    for table, columns in candidates.items():
        rows = load_columns(root / table, set(columns))
        for column in columns:
            values = [normalize_key(row[column]) for row in rows]
            nonblank = [value for value in values if value]
            counts: dict[str, int] = {}
            for value in nonblank:
                counts[value] = counts.get(value, 0) + 1
            result.append(
                {
                    "tabela": table,
                    "campo": column,
                    "linhas": len(rows),
                    "vazios": len(rows) - len(nonblank),
                    "distintos_preenchidos": len(counts),
                    "chaves_duplicadas": sum(count > 1 for count in counts.values()),
                    "linhas_em_chaves_duplicadas": sum(
                        count for count in counts.values() if count > 1
                    ),
                }
            )
    return result


def write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(source: Path, output: Path, workers: int) -> None:
    all_files = [path for path in source.rglob("*") if path.is_file()]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        dbf_flags = list(executor.map(is_dbf_format, all_files))
    dbf_format_files = [path for path, is_dbf in zip(all_files, dbf_flags, strict=True) if is_dbf]
    layouts = [parse_layout(path) for path in dbf_format_files]

    current_tables = sorted(source.glob("*.DBF"), key=lambda path: path.name.upper())
    with ThreadPoolExecutor(max_workers=workers) as executor:
        profiles = list(executor.map(lambda path: profile_table(path, source), current_tables))

    dictionary = {
        "gerado_em": datetime.now().astimezone().isoformat(),
        "fonte": str(source),
        "arquivos_dbf_ativos": len(current_tables),
        "arquivos_em_formato_dbf": len(layouts),
        "arquivos_dbf_com_extensao_alternativa": sum(
            layout.path.suffix.upper() != ".DBF" for layout in layouts
        ),
        "tabelas": [layout_document(layout, source) for layout in layouts],
    }
    quality = {
        "gerado_em": datetime.now().astimezone().isoformat(),
        "resumo": {
            "tabelas": len(profiles),
            "registros_ativos": sum(profile["registros_ativos"] for profile in profiles),
            "duplicados_exatos": sum(
                profile["registros_duplicados_exatos"] for profile in profiles
            ),
            "datas_invalidas": sum(profile["datas_invalidas"] for profile in profiles),
            "datas_implausiveis": sum(
                profile["datas_formalmente_validas_mas_implausiveis"] for profile in profiles
            ),
            "numericos_invalidos": sum(profile["numericos_invalidos"] for profile in profiles),
        },
        "tabelas": profiles,
        "chaves_candidatas": key_profile(source),
    }
    relationships = {
        "gerado_em": datetime.now().astimezone().isoformat(),
        **relationship_profile(source),
        "observacao": "Relacionamentos inferidos; DBF nao declara chaves estrangeiras.",
    }
    write_json(output / "fase_2_dicionario_dados.json", dictionary)
    write_json(output / "fase_2_qualidade_dados.json", quality)
    write_json(output / "fase_2_relacionamentos.json", relationships)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventaria bancos DBF sem exportar dados pessoais."
    )
    parser.add_argument("--source", type=Path, default=Path("ABEL-BAK"))
    parser.add_argument("--output", type=Path, default=Path("docs"))
    parser.add_argument("--workers", type=int, default=min(32, max(4, (os.cpu_count() or 2) * 2)))
    args = parser.parse_args()
    run(args.source.resolve(), args.output.resolve(), args.workers)


if __name__ == "__main__":
    main()
