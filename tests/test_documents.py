from datetime import date
from io import BytesIO

import pytest
from backend.app.api.dependencies import AuthContext
from backend.app.api.routes.documents import (
    can_access_appointment,
    masked_destination,
    validate_pdf,
)
from backend.app.db.models import Appointment, AuthSession, Patient, User
from pypdf import PdfWriter


def make_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


def test_real_pdf_is_parsed() -> None:
    assert validate_pdf(make_pdf()) == 1


def test_renamed_or_malformed_file_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_pdf(b"arquivo de texto renomeado.pdf")
    with pytest.raises(ValueError):
        validate_pdf(b"%PDF-1.7\nconteudo corrompido")


def test_delivery_destination_is_masked() -> None:
    patient = Patient(name="Paciente", phone="11987654321", email="pessoa@example.com")
    assert masked_destination(patient, "telefone") == "***4321"
    assert masked_destination(patient, "whatsapp_manual") == "***4321"
    assert masked_destination(patient, "email_manual") == "p***@example.com"
    assert masked_destination(patient, "presencial") == "presencial"


def test_document_access_is_limited_to_assigned_professional() -> None:
    user = User(id=8, username="medico", display_name="Medico", professional_id=12)
    context = AuthContext(
        user=user,
        session=AuthSession(id=1, user_id=8),
        roles=frozenset({"medico"}),
    )
    own = Appointment(id=1, patient_id=1, exam_date=date(2026, 11, 2), doctor_id=12)
    other = Appointment(id=2, patient_id=1, exam_date=date(2026, 11, 2), doctor_id=99)
    assert can_access_appointment(context, own) is True
    assert can_access_appointment(context, other) is False
