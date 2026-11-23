import json

import pytest

from app.extraction import extractor
from app.extraction.fixtures import FEB_25


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "bill.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return str(p)


def test_mock_mode(monkeypatch, pdf):
    monkeypatch.setenv("EXTRACTION_MODE", "mock")
    assert extractor.extract_bill(pdf)["consumer"]["rr_number"] == "KULHT15"


def test_missing_api_key_is_fatal(monkeypatch, pdf):
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(extractor.ExtractionError, match="GEMINI_API_KEY"):
        extractor.extract_bill(pdf)


def test_retries_bad_json_then_succeeds(monkeypatch, pdf):
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    replies = iter(["not json {", json.dumps(FEB_25)])
    monkeypatch.setattr(extractor, "_call_gemini", lambda data, mime, *args, **kwargs: next(replies))
    assert extractor.extract_bill(pdf)["billing"]["bill_month_label"] == "Feb-25"


def test_gives_up_after_retries(monkeypatch, pdf):
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    monkeypatch.setattr(extractor, "_call_gemini", lambda data, mime, *args, **kwargs: "{}")
    with pytest.raises(extractor.ExtractionError, match="attempts"):
        extractor.extract_bill(pdf)


def test_not_a_bill_is_fatal_and_not_retried(monkeypatch, pdf):
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    calls = []
    bad = {**FEB_25, "extraction_notes": {"page_used": 1, "unclear_fields": [], "document_is_mescom_bill": False}}

    def fake(data, mime, *args, **kwargs):
        calls.append(1)
        return json.dumps(bad)
    monkeypatch.setattr(extractor, "_call_gemini", fake)
    with pytest.raises(extractor.ExtractionError, match="MESCOM"):
        extractor.extract_bill(pdf)
    assert len(calls) == 1


def test_unsupported_extension(monkeypatch, tmp_path):
    monkeypatch.delenv("EXTRACTION_MODE", raising=False)
    p = tmp_path / "bill.docx"
    p.write_bytes(b"x")
    with pytest.raises(extractor.ExtractionError, match="Unsupported"):
        extractor.extract_bill(str(p))
