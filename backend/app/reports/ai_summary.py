"""AI-Written Executive Summary generator with strict numerical guardrails.

Requirement: Every number in the generated summary MUST be passed in from calculated
data, and the output is strictly validated to ensure no hallucinated figures appear.
"""
from datetime import date
from decimal import Decimal
import json
import os
import re
from typing import Optional

from .. import config


def _normalize_num(n: str) -> str:
    # Remove commas, trailing .0, etc.
    s = n.replace(",", "").strip()
    try:
        f = float(s)
        return f"{f:g}"
    except ValueError:
        return s


def verify_summary_numbers(text: str, allowed_numbers: set[str]) -> tuple[bool, list[str]]:
    """Extract all numbers from text and check that each exists in allowed_numbers."""
    # Find all standalone numbers (integers or decimals)
    found = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    unauthorized = []
    
    # Normalized allowed set
    norm_allowed = set()
    for item in allowed_numbers:
        norm_allowed.add(_normalize_num(str(item)))
        
    for num in found:
        norm_n = _normalize_num(num)
        if norm_n not in norm_allowed:
            unauthorized.append(num)

    return (len(unauthorized) == 0, unauthorized)


def deterministic_summary(data: dict) -> str:
    """High-quality deterministic summary using only verified calculated data."""
    start = data.get("start_str", "")
    end = data.get("end_str", "")
    solar = data.get("solar_generated", "0")
    imported = data.get("imported", "0")
    exported = data.get("exported", "0")
    net = data.get("net_energy", "0")
    consumed = data.get("total_consumed", "0")
    savings = data.get("savings", "0")
    months = data.get("months_included", 1)

    savings_text = f"Rs {savings}" if savings else "Pending savings rate input"

    return (
        f"During the period from {start} to {end} ({months} months), the college rooftop solar system "
        f"generated a total of {solar} Units (kWh) of clean electricity. The campus imported {imported} Units from "
        f"MESCOM and exported {exported} Units back to the grid, resulting in a net grid import of {net} Units. "
        f"Total electrical consumption across the campus was {consumed} Units.\n\n"
        f"The on-site solar generation delivered an estimated cost savings of {savings_text}. "
        f"The rooftop installation continues to offset high-tariff utility imports and contribute to sustainable campus operations."
    )


def generate_executive_summary(data: dict, model: Optional[str] = None) -> dict:
    """Generate summary using Gemini, with verification guardrails."""
    # Gather all allowed figures
    allowed_numbers = set()
    
    # Add input numbers
    for k in ("solar_generated", "imported", "exported", "net_energy", "total_consumed", "savings", "months_included"):
        val = data.get(k)
        if val is not None:
            allowed_numbers.add(str(val))
            # Also allow rounded integer version
            try:
                allowed_numbers.add(str(int(Decimal(str(val)))))
            except Exception:
                pass

    # Add years and calendar numbers 2020..2030, days 1..31
    for y in range(2020, 2035):
        allowed_numbers.add(str(y))
    for d in range(1, 32):
        allowed_numbers.add(str(d))

    if config.extraction_mode() == "mock" or not os.getenv("GEMINI_API_KEY"):
        summary_text = deterministic_summary(data)
        return {
            "summary": summary_text,
            "guardrail_passed": True,
            "unauthorized_numbers": [],
            "source": "deterministic_fallback",
        }

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options=types.HttpOptions(timeout=20000))
    active_model = model or config.gemini_model()

    prompt = f"""You are an expert energy auditor writing an executive summary of rooftop solar generation for college leadership.

Here are the EXACT verified data points for the period {data.get('start_str')} to {data.get('end_str')}:
- Total Solar Generation: {data.get('solar_generated')} Units
- Total Energy Imported from MESCOM: {data.get('imported')} Units
- Total Energy Exported to MESCOM: {data.get('exported')} Units
- Net Energy Imported from MESCOM: {data.get('net_energy')} Units
- Total Electrical Energy Consumption: {data.get('total_consumed')} Units
- Total Cost Savings: Rs {data.get('savings', 'N/A')}
- Number of Months: {data.get('months_included')}

STRICT RULES:
1. You must ONLY use the exact figures listed above or the calendar years/dates in the period.
2. DO NOT calculate, approximate, or mention ANY other numbers, percentages, or statistics.
3. Write exactly two concise paragraphs:
   - Paragraph 1: Solar generation output, grid import/export, and campus consumption.
   - Paragraph 2: Financial savings impact and clean energy offset.
"""

    for attempt_model in [active_model] + config.gemini_models():
        try:
            resp = client.models.generate_content(
                model=attempt_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            raw_text = (resp.text or "").strip()
            passed, unauthorized = verify_summary_numbers(raw_text, allowed_numbers)
            if passed:
                return {
                    "summary": raw_text,
                    "guardrail_passed": True,
                    "unauthorized_numbers": [],
                    "source": f"gemini:{attempt_model}",
                }
            else:
                # If guardrail caught unauthorized numbers, use deterministic fallback for guaranteed accuracy
                return {
                    "summary": deterministic_summary(data),
                    "guardrail_passed": False,
                    "unauthorized_numbers": unauthorized,
                    "source": "deterministic_fallback_guardrail_triggered",
                }
        except Exception:
            continue

    # Fallback if API fails
    return {
        "summary": deterministic_summary(data),
        "guardrail_passed": True,
        "unauthorized_numbers": [],
        "source": "deterministic_fallback",
    }
