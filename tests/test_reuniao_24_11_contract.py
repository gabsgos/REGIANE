import json
from pathlib import Path

from backend.app.api.routes.finance import PaymentCreate
from backend.app.api.routes.operations import IntakeIn, IntakeOut
from backend.app.api.routes.schedule import ExtraIn
from backend.app.main import create_app


def test_intake_fixture_matches_frozen_contract():
    fixture = Path(__file__).parent / "fixtures" / "reuniao_24_11_contract.json"
    payload = IntakeIn.model_validate(json.loads(fixture.read_text(encoding="utf-8")))

    assert payload.patient.cpf == "52998224725"
    assert [service.service_code for service in payload.services] == [
        "MEDICAL_EXAM",
        "PSYCHOTECHNICAL",
    ]


def test_intake_response_supports_created_and_reused_records():
    result = IntakeOut.model_validate(
        {
            "patient_id": 1,
            "patient_created": False,
            "idempotent": True,
            "appointments": [
                {
                    "id": 2,
                    "service_code": "MEDICAL_EXAM",
                    "professional_id": 10,
                    "scheduled_at": "2026-11-25T08:00:00",
                    "created": False,
                }
            ],
        }
    )

    assert result.idempotent is True
    assert result.appointments[0].created is False


def test_sanitized_new_patient_return_and_hybrid_payment_fixtures():
    fixture_dir = Path(__file__).parent / "fixtures"
    new_patient = IntakeIn.model_validate(
        json.loads(
            (fixture_dir / "reuniao_24_11_intake_new_patient.json").read_text(encoding="utf-8")
        )
    )
    return_request = ExtraIn.model_validate(
        json.loads((fixture_dir / "reuniao_24_11_return.json").read_text(encoding="utf-8"))
    )
    hybrid_payment = PaymentCreate.model_validate(
        json.loads((fixture_dir / "reuniao_24_11_hybrid_payment.json").read_text(encoding="utf-8"))
    )

    assert new_patient.patient.cpf is None
    assert return_request.previous_appointment_id == 100
    assert [item.method for item in hybrid_payment.items] == ["pix", "dinheiro"]


def test_openapi_exposes_intake_contract_on_abel_prefix():
    schema = create_app().openapi()
    operation = schema["paths"]["/abel/api/operations/intakes"]["post"]

    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/IntakeIn"
    )
    assert "201" in operation["responses"]
    assert "/abel/api/operations/patients/{patient_id}/journey" in schema["paths"]
    assert "/abel/api/operations/appointments/{appointment_id}/checkout" in schema["paths"]
    assert "/abel/api/finance/appointments/{appointment_id}/checkout" in schema["paths"]
    assert (
        "/abel/api/operations/schedule/professionals/{professional_id}/availability"
        in schema["paths"]
    )
    assert (
        "/abel/api/operations/patients/{patient_id}/appointments/return-eligible" in schema["paths"]
    )
