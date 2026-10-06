from pathlib import Path
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def generate_certificate(
    *,
    recipient_name: str,
    event_name: str,
    completion_date,
    output_path: Path,
    certificate_id: UUID,
) -> Path:
    """Generate a single certificate PDF and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))

    # Page background and decorative border.
    pdf.setFillColor(colors.HexColor("#FAF8F1"))
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    pdf.setStrokeColor(colors.HexColor("#B08D57"))
    pdf.setLineWidth(2)
    pdf.rect(12 * mm, 12 * mm, page_width - 24 * mm, page_height - 24 * mm)

    pdf.setStrokeColor(colors.HexColor("#D7BC83"))
    pdf.setLineWidth(0.8)
    pdf.rect(16 * mm, 16 * mm, page_width - 32 * mm, page_height - 32 * mm)

    # Certificate heading.
    pdf.setFillColor(colors.HexColor("#26354A"))
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 45 * mm,
        "CERTIFICATE OF COMPLETION",
    )

    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 62 * mm,
        "This certificate is proudly presented to",
    )

    # Recipient name.
    pdf.setFillColor(colors.HexColor("#172B4D"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 82 * mm,
        recipient_name,
    )

    # Event and completion date.
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 98 * mm,
        f"for successfully completing {event_name}",
    )
    pdf.drawCentredString(
        page_width / 2,
        page_height - 110 * mm,
        f"Completion date: {completion_date.isoformat()}",
    )

    # Certificate reference.
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(
        page_width / 2,
        23 * mm,
        f"Certificate ID: {certificate_id}",
    )

    pdf.save()
    return output_path
