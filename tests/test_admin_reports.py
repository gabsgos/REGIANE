from datetime import date

import pytest
from backend.app.api.routes.admin_reports import UserCreate, safe_csv
from pydantic import ValidationError


def test_csv_formula_injection_is_neutralized() -> None:
    assert safe_csv("=SUM(A1:A2)").startswith("'")
    assert safe_csv("+cmd").startswith("'")
    assert safe_csv("Paciente normal") == "Paciente normal"


def test_user_create_schema_accepts_only_known_roles() -> None:
    item = UserCreate(
        username="novo.usuario",
        display_name="Novo Usuario",
        cpf="52998224725",
        birth_date=date(1990, 1, 1),
        phone="11999999999",
        email="novo@example.com",
        address="Rua de Teste, 123",
        role="atendente",
    )
    assert item.role == "atendente"
    assert item.cpf == "52998224725"


def test_user_create_rejects_invalid_cpf() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            username="cpf.invalido",
            display_name="CPF Invalido",
            cpf="11111111111",
            birth_date=date(1990, 1, 1),
            phone="11999999999",
            email="cpf@example.com",
            address="Rua de Teste, 123",
            role="atendente",
        )
