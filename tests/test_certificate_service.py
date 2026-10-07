from datetime import date
from uuid import uuid4

from bulk_certificate_generator.services.certificate_service import generate_certificate


def test_generate_certificate_creates_pdf_in_nested_directory(tmp_path):
    certificate_id = uuid4()
    output_path = tmp_path / "nested" / "certificates" / "certificate.pdf"

    result = generate_certificate(
        recipient_name="Ada Lovelace",
        event_name="Python Workshop",
        completion_date=date(2026, 10, 1),
        output_path=output_path,
        certificate_id=certificate_id,
    )

    assert result == output_path
    assert output_path.is_file()

    pdf_bytes = output_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 100
    assert b"%%EOF" in pdf_bytes


def test_generate_certificate_creates_distinct_files_for_distinct_ids(
    tmp_path,
):
    first_id = uuid4()
    second_id = uuid4()

    first_path = tmp_path / f"{first_id}.pdf"
    second_path = tmp_path / f"{second_id}.pdf"

    common_args = {
        "recipient_name": "Grace Hopper",
        "event_name": "Python Workshop",
        "completion_date": date(2026, 10, 1),
    }

    generate_certificate(
        **common_args,
        output_path=first_path,
        certificate_id=first_id,
    )
    generate_certificate(
        **common_args,
        output_path=second_path,
        certificate_id=second_id,
    )

    assert first_path.is_file()
    assert second_path.is_file()
    assert first_path != second_path
    assert first_path.read_bytes().startswith(b"%PDF-")
    assert second_path.read_bytes().startswith(b"%PDF-")
