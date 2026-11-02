from datetime import date
from decimal import Decimal

from tools.normalize_legacy import clean, digits, money, name_key, parse_date


def test_legacy_value_helpers() -> None:
    assert clean("  ABC  ", 2) == "AB"
    assert digits("123.456-7") == "1234567"
    assert name_key("  Maria   da Silva ") == "MARIA DA SILVA"
    assert parse_date("20261031") == date(2026, 10, 31)
    assert parse_date("20261331") is None
    assert money("1.234,56") == Decimal("1234.56")
    assert money("1234.56") == Decimal("1234.56")
    assert money("") == Decimal("0.00")
