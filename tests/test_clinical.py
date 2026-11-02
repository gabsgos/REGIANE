from pathlib import Path

import pytest
from backend.app.api.routes.clinical import (
    PatientCreate,
    ReanalysisRequest,
    cpf_digits,
    valid_cpf,
)
from pydantic import ValidationError


def test_cpf_validation_and_normalization() -> None:
    assert cpf_digits("529.982.247-25") == "52998224725"
    assert valid_cpf("52998224725") is True
    assert valid_cpf("11111111111") is False
    assert PatientCreate(name="Paciente Teste", cpf="529.982.247-25").cpf == "52998224725"


def test_invalid_cpf_is_rejected_but_missing_is_allowed() -> None:
    assert PatientCreate(name="Paciente Legado", cpf=None).cpf is None
    with pytest.raises(ValidationError):
        PatientCreate(name="Paciente Teste", cpf="123")


def test_reanalysis_requires_meaningful_observation() -> None:
    request = ReanalysisRequest(expected_version=2, observation="Revisar acuidade")
    assert request.expected_version == 2
    with pytest.raises(ValidationError):
        ReanalysisRequest(expected_version=2, observation="x")


def test_clinical_worklist_payload_does_not_expose_finance() -> None:
    source = Path("backend/app/api/routes/clinical.py").read_text(encoding="utf-8")
    worklist = source.split('def clinical_worklist(', 1)[1].split('@router.post(', 1)[0]
    for forbidden in ("total_amount", "paid_at", "payment_method", "receipt_number"):
        assert forbidden not in worklist
