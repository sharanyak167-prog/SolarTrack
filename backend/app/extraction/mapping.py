"""Turn the extraction JSON into flat values matching the database columns."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


def _dec(x) -> Optional[Decimal]:
    return None if x is None else Decimal(str(x))


def _date(s) -> Optional[date]:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def parse_month_label(label: Optional[str], fallback: Optional[date]) -> Optional[date]:
    """'Feb-25' -> 2025-02-01. Falls back to the month of the period start."""
    if label:
        for fmt in ("%b-%y", "%b-%Y", "%B-%Y", "%b %Y", "%b %y", "%B %Y"):
            try:
                d = datetime.strptime(label.strip(), fmt)
                return date(d.year, d.month, 1)
            except ValueError:
                continue
    return fallback.replace(day=1) if fallback else None


def to_bill_fields(x: dict) -> tuple[dict, dict]:
    """Returns (connection_fields, bill_fields)."""
    c = x.get("consumer") or {}
    b = x.get("billing") or {}
    m = x.get("meters") or {}
    notes = x.get("extraction_notes") or {}
    imp = m.get("grid_import") or {}
    exp = m.get("solar_export") or {}
    sol = m.get("solar_generation") or {}

    period_start = _date(b.get("previous_reading_date"))
    period_end = _date(b.get("present_reading_date"))

    connection = {
        "rr_number": (c.get("rr_number") or "").strip() or None,
        "account_id": c.get("account_id"),
        "consumer_name": c.get("name"),
        "tariff": c.get("tariff"),
        "voltage_class": c.get("voltage_class"),
        "contract_demand_kva": _dec(c.get("contract_demand_kva")),
        "meter_constant": _dec(c.get("meter_constant")),
        "solar_constant": _dec(c.get("solar_constant")),
    }
    bill = {
        "page_used": notes.get("page_used") or 1,
        "bill_month": parse_month_label(b.get("bill_month_label"), period_start),
        "bill_month_label": b.get("bill_month_label"),
        "period_start": period_start,
        "period_end": period_end,
        "bill_date": _date(b.get("bill_date")),
        "due_date": _date(b.get("due_date")),
        "meter_constant": connection["meter_constant"],
        "solar_constant": connection["solar_constant"],
        "import_prev": _dec(imp.get("previous_reading")),
        "import_present": _dec(imp.get("present_reading")),
        "import_units_printed": _dec(imp.get("units_printed")),
        "export_prev": _dec(exp.get("previous_reading")),
        "export_present": _dec(exp.get("present_reading")),
        "export_units_printed": _dec(exp.get("units_printed")),
        "solar_prev": _dec(sol.get("previous_reading")),
        "solar_present": _dec(sol.get("present_reading")),
        "solar_units_printed": _dec(sol.get("units_printed")),
        "net_import_printed": _dec(m.get("net_energy_import_printed")),
        "net_export_printed": _dec(m.get("net_energy_export_printed")),
        "sub_meter_units": _dec(m.get("sub_meter_consumption")),
        "recorded_demand_kva": _dec(m.get("recorded_demand_kva")),
        "power_factor": _dec(m.get("power_factor")),
        "kvah_raw": m.get("kvah_values"),
        "unclear_fields": notes.get("unclear_fields") or [],
    }
    return connection, bill
