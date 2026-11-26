from decimal import Decimal

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.finance import (
    PaymentCreate,
    PaymentItemIn,
    appointment_checkout,
    create_payment,
)
from backend.app.db.models import Appointment, AuthSession, Payment, ServiceType, User
from fastapi import HTTPException
from sqlalchemy.orm import Session

pytest_plugins = ("tests.test_workspace_scope",)


@pytest.fixture
def checkout_db(database):
    with Session(database) as db:
        db.info["workspace_id"] = 1
        db.add(
            ServiceType(
                id=1,
                workspace_id=1,
                code="MEDICAL_EXAM",
                name="Exame medico",
                price=Decimal("100.00"),
            )
        )
        appointment = db.get(Appointment, 1)
        appointment.service_type_id = 1
        existing = db.get(Payment, 1)
        db.delete(existing)
        db.commit()
        yield db


def context():
    return AuthContext(
        user=User(id=1, workspace_id=1),
        session=AuthSession(),
        roles=frozenset({"atendente"}),
    )


def payment(total="100.00", *, hybrid=False):
    items = (
        [
            PaymentItemIn(method="dinheiro", amount=Decimal("40.00")),
            PaymentItemIn(method="pix", amount=Decimal("60.00"), reference="PIX-SINTETICO"),
        ]
        if hybrid
        else [PaymentItemIn(method="dinheiro", amount=Decimal(total))]
    )
    return PaymentCreate(appointment_id=1, total_amount=Decimal(total), items=items)


def test_checkout_is_derived_from_appointment_service(checkout_db):
    result = appointment_checkout(1, context(), checkout_db)

    assert result.patient_id == 1
    assert result.service_code == "MEDICAL_EXAM"
    assert result.professional_id == 1
    assert result.total_amount == "100.00"
    assert result.payment_status == "pendente"


def test_payment_rejects_client_total_different_from_service_price(checkout_db):
    with pytest.raises(HTTPException, match="preco configurado"):
        create_payment(payment("90.00"), context(), checkout_db)


def test_hybrid_payment_uses_server_price_and_blocks_duplicate(checkout_db):
    result = create_payment(payment(hybrid=True), context(), checkout_db)

    assert result["total_amount"] == "100.00"
    assert [item["method"] for item in result["items"]] == ["dinheiro", "pix"]
    with pytest.raises(HTTPException, match="pagamento ativo"):
        create_payment(payment(), context(), checkout_db)
