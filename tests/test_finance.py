from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from backend.app.api.routes.finance import (
    PaymentCreate,
    business_today,
    payment_period_filters,
    utc_day_bounds,
    validate_report_period,
)
from fastapi import HTTPException
from pydantic import ValidationError


def test_hybrid_payment_requires_exact_sum() -> None:
    payment = PaymentCreate(
        appointment_id=1,
        total_amount=Decimal("100.00"),
        items=[
            {"method": "pix", "amount": "60.00"},
            {"method": "dinheiro", "amount": "40.00"},
        ],
    )
    assert sum(item.amount for item in payment.items) == payment.total_amount


def test_payment_rejects_mismatch_and_negative_values() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(
            appointment_id=1,
            total_amount=Decimal("100.00"),
            items=[{"method": "pix", "amount": "99.00"}],
        )
    with pytest.raises(ValidationError):
        PaymentCreate(
            appointment_id=1,
            total_amount=Decimal("-1.00"),
            items=[{"method": "pix", "amount": "-1.00"}],
        )


def test_financial_day_uses_sao_paulo_boundaries_in_utc() -> None:
    assert business_today(datetime(2026, 11, 2, 0, 9, tzinfo=UTC)) == date(2026, 11, 1)
    assert utc_day_bounds(date(2026, 11, 1), date(2026, 11, 1)) == (
        datetime(2026, 11, 1, 3),
        datetime(2026, 11, 2, 3),
    )


def test_financial_report_rejects_inverted_period() -> None:
    with pytest.raises(HTTPException) as error:
        validate_report_period(date(2026, 11, 2), date(2026, 11, 1))
    assert error.value.status_code == 422


def test_financial_report_filters_include_optional_user() -> None:
    without_user = payment_period_filters(date(2026, 11, 1), date(2026, 11, 1))
    with_user = payment_period_filters(date(2026, 11, 1), date(2026, 11, 1), 7)
    assert len(without_user) == 2
    assert len(with_user) == 3
