"""Tests for PDF report generation and AI summary guardrails."""
from datetime import date
from decimal import Decimal
import pypdf
import io
import pytest

from app.reports.ai_summary import deterministic_summary, verify_summary_numbers
from app.reports.generator import generate_report_pdf


def test_numerical_guardrail_validator():
    allowed = {"37102", "77196", "2610", "74586", "111688", "259714", "7", "2025"}
    
    # Valid summary using only allowed numbers
    valid_text = "In 2025, solar produced 37102 units and campus imported 77196 units at rate 7."
    passed, bad = verify_summary_numbers(valid_text, allowed)
    assert passed is True
    assert bad == []

    # Invalid summary introducing an unauthorized hallucinated number (e.g. 99999 or 45.2)
    invalid_text = "Solar produced 37102 units resulting in 99999 unexpected savings."
    passed, bad = verify_summary_numbers(invalid_text, allowed)
    assert passed is False
    assert "99999" in bad


def test_deterministic_summary():
    data = {
        "start_str": "01 March 2025",
        "end_str": "31 March 2025",
        "solar_generated": "37102",
        "imported": "77196",
        "exported": "2610",
        "net_energy": "74586",
        "total_consumed": "111688",
        "savings": "259714",
        "months_included": 1,
    }
    s = deterministic_summary(data)
    assert "37102" in s
    assert "77196" in s
    assert "259714" in s


def test_generate_report_pdf():
    months = [
        {
            "bill_month": "2025-03-01",
            "month_label": "Mar-25",
            "rate_per_unit": Decimal("7"),
            "energy": {
                "solar_generated": Decimal("37102"),
                "imported": Decimal("77196"),
                "exported": Decimal("2610"),
                "net_energy": Decimal("74586"),
                "total_consumed": Decimal("111688"),
                "savings": Decimal("259714"),
            },
        }
    ]
    summary = {
        "months_included": 1,
        "total": {
            "solar_generated": Decimal("37102"),
            "imported": Decimal("77196"),
            "exported": Decimal("2610"),
            "net_energy": Decimal("74586"),
            "total_consumed": Decimal("111688"),
            "savings": Decimal("259714"),
        },
    }

    pdf_bytes = generate_report_pdf(
        connection_details={"rr_number": "KULHT15"},
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 31),
        months_data=months,
        summary_data=summary,
        include_ai_summary=True,
    )

    assert pdf_bytes.startswith(b"%PDF-")
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    page1_text = reader.pages[0].extract_text()
    assert "Details of Energy Generated from Solar Roof Top System" in page1_text
    assert "37,102" in page1_text or "37102" in page1_text
    assert "77,196" in page1_text or "77196" in page1_text
