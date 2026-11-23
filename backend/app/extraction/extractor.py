"""Bill extraction. Gemini only READS what is printed; all arithmetic happens elsewhere."""
import json
import time
from copy import deepcopy
from pathlib import Path

from .. import config
from .fixtures import FEB_25

SCHEMA_PATH = Path(__file__).with_name("extraction_schema.json")

PROMPT = """You are reading a MESCOM (Mangalore Electricity Supply Company) HT electricity bill.
Extract the fields in the response schema EXACTLY as printed on the bill.

Rules:
- Copy numbers exactly. No commas. Do not calculate, round or correct anything.
- If a value is blurry, overlapping, or you are not sure, still give your best reading,
  and add its dotted path (e.g. meters.solar_generation.present_reading) to extraction_notes.unclear_fields.
  If a field is not on the bill at all, use null.
- Dates must be YYYY-MM-DD (the bill prints DD.MM.YYYY).
- The file may have several pages. Use the page that holds the bill itself and report it in extraction_notes.page_used.
- grid_import: use the 'Total Consumption' row of the IMPORT ENERGY block (not the time-of-day rows).
- solar_export: use the 'Units' row of the SOLAR EXPORT ENERGY block.
- solar_generation: the 'Solar Generation Meter' block at the top right. In this block, the numbers printed in order are: present_reading (e.g. 14478.19), previous_reading (e.g. 14107.17), and units_printed (e.g. 37102.00). Note that present_reading is >= previous_reading.
- If the document is not a MESCOM electricity bill, set document_is_mescom_bill to false.
"""


class ExtractionError(Exception):
    """Fatal: retrying will not help (no API key, wrong file type, not a bill)."""


class _BadOutput(Exception):
    """Gemini returned something unusable; worth a retry."""


def _load_schema() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text())
    schema.pop("_comment", None)
    return schema


def _call_gemini(data: bytes, mime: str, model: str | None = None) -> str:
    import os
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ExtractionError("GEMINI_API_KEY is not set on the server")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
    response = client.models.generate_content(
        model=model or config.gemini_model(),
        contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_load_schema(),
            temperature=0,
        ),
    )
    return response.text


def _check_shape(obj: dict) -> None:
    if not isinstance(obj, dict):
        raise _BadOutput("response is not a JSON object")
    for key in ("consumer", "billing", "meters", "extraction_notes"):
        if not isinstance(obj.get(key), dict):
            raise _BadOutput(f"missing section '{key}'")
    if obj["extraction_notes"].get("document_is_mescom_bill") is False:
        raise ExtractionError("This file does not look like a MESCOM electricity bill")


_sleep = time.sleep
TRANSIENT_CODES = {429, 500, 502, 503, 504}   # busy / rate limited / server hiccup
MAX_BAD_OUTPUT = 3                              # unusable JSON: retry at most this many times


def _is_transient(e: Exception) -> bool:
    """True for errors worth retrying after a pause (Google busy, rate limit, network)."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in TRANSIENT_CODES:
        return True
    s = str(e).lower()
    if any(term in s for term in ("503", "429", "unavailable", "high demand", "overloaded", "deadline expired", "resource exhausted")):
        return True
    return (isinstance(e, (TimeoutError, ConnectionError))
            or type(e).__module__.startswith("httpx"))


class _Busy(ExtractionError):
    """The model stayed busy / rate limited through every retry. Another model may work."""


def _extract_with_model(data: bytes, mime: str, model: str, max_attempts: int) -> dict:
    last: Exception | None = None
    bad_outputs = 0
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            obj = json.loads(_call_gemini(data, mime, model))
            _check_shape(obj)
            return obj
        except ExtractionError:
            raise
        except (json.JSONDecodeError, _BadOutput) as e:
            last = e
            bad_outputs += 1
            if bad_outputs >= MAX_BAD_OUTPUT:
                break
        except Exception as e:
            last = e
            if not _is_transient(e):
                raise ExtractionError(f"Gemini request failed ({model}): {e}") from e
            if attempt < max_attempts:
                _sleep(min(2 ** attempt, 16))
            elif attempt == max_attempts:
                raise _Busy(f"Extraction failed after {attempt} attempts ({model}): {last}") from e
    raise ExtractionError(f"Extraction failed after {attempt} attempts ({model}): {last}")


def extract_bill(file_path: str, max_attempts: int = 5, page_num: int | None = None) -> dict:
    """Return extraction JSON (shape of extraction_schema.json) for a bill file.

    Busy/rate-limit errors are retried with a growing pause (2s, 4s, 8s, 16s). If the main
    model stays busy, each model in GEMINI_FALLBACK_MODELS is tried in turn.
    Permanent errors (bad key, unknown model, bad request) fail immediately.
    For multi-page PDFs, page_num (1-indexed) selects a specific page.
    """
    if config.extraction_mode() == "mock":
        return deepcopy(FEB_25)

    path = Path(file_path)
    ext = path.suffix.lower()
    mime = config.ALLOWED_TYPES.get(ext)
    if mime is None:
        raise ExtractionError(f"Unsupported file type '{path.suffix}'")
    data = path.read_bytes()

    actual_page_used = 1
    if ext == ".pdf":
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(data))
            total_pages = len(reader.pages)
            if total_pages > 1:
                target_idx = (page_num - 1) if (page_num and 1 <= page_num <= total_pages) else 0
                actual_page_used = target_idx + 1
                page = reader.pages[target_idx]
                if page.images:
                    data = page.images[0].data
                    mime = "image/jpeg"
                else:
                    writer = pypdf.PdfWriter()
                    writer.add_page(page)
                    buf = io.BytesIO()
                    writer.write(buf)
                    data = buf.getvalue()
                    mime = "application/pdf"
        except Exception:
            pass

    models = config.gemini_models()
    tried: list[str] = []
    for model in models:
        try:
            res = _extract_with_model(data, mime, model, max_attempts)
            if "extraction_notes" in res:
                res["extraction_notes"]["page_used"] = actual_page_used
            return res
        except _Busy as e:
            tried.append(str(e))
    raise ExtractionError(" | ".join(tried) if len(tried) > 1 else (tried[0] if tried else "All models failed"))
