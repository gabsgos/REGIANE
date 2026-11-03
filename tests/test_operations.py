from decimal import Decimal

import pytest
from backend.app.api.routes.finance import PaymentCreate
from backend.app.api.routes.operations import FinalizeIn, StrictPatientCreate, _source_key
from pydantic import ValidationError


def test_new_patient_contract_requires_name_birth_date_and_valid_cpf() -> None:
    patient = StrictPatientCreate(
        name="Paciente Teste", birth_date="1990-01-02", cpf="529.982.247-25"
    )
    assert patient.cpf == "52998224725"
    with pytest.raises(ValidationError):
        StrictPatientCreate(name="Paciente Teste", cpf="52998224725")


def test_temporary_unfit_requires_reason_or_observation() -> None:
    with pytest.raises(ValidationError):
        FinalizeIn(outcome="TEMPORARILY_UNFIT")
    result = FinalizeIn(outcome="TEMPORARILY_UNFIT", rejection_reason="DOCUMENTATION_MISSING")
    assert result.missing_documents is False


def test_agenda_source_key_is_stable_and_row_specific() -> None:
    digest = "a" * 64
    assert _source_key(digest, 1) == _source_key(digest, 1)
    assert _source_key(digest, 1) != _source_key(digest, 2)


def test_only_cash_pix_and_exact_split_are_accepted() -> None:
    payment = PaymentCreate(
        appointment_id=1,
        total_amount=Decimal("100.00"),
        items=[{"method": "dinheiro", "amount": "40.00"}, {"method": "pix", "amount": "60.00"}],
    )
    assert sum(item.amount for item in payment.items) == payment.total_amount
    with pytest.raises(ValidationError):
        PaymentCreate(
            appointment_id=1,
            total_amount="100.00",
            items=[{"method": "cartao", "amount": "100.00"}],
        )


def test_completed_is_independent_from_payment_payload() -> None:
    result = FinalizeIn(outcome="COMPLETED")
    assert result.outcome == "COMPLETED"
    assert not hasattr(result, "payment_id")
