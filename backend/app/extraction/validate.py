"""Checks run on every extracted or edited bill. See docs/FORMULAS.md.

Input is a flat dict with the Bill column names (Decimals / dates).
`previous` is the same shape for the previous month's bill, or None.
Severity 'error' blocks verification; 'warning' asks the reviewer to look.
"""
from decimal import Decimal

TOL = Decimal("1")  # kWh tolerance between computed and printed units

REQUIRED = [
    "bill_month", "period_start", "period_end", "meter_constant", "solar_constant",
    "import_prev", "import_present", "import_units_printed",
    "export_prev", "export_present", "export_units_printed",
    "solar_prev", "solar_present", "solar_units_printed",
]
METERS = (("import", "meter_constant"), ("export", "meter_constant"), ("solar", "solar_constant"))


def _flag(code: str, severity: str, field: str, message: str) -> dict:
    return {"code": code, "severity": severity, "field": field, "message": message}


def missing_required(b: dict) -> list[str]:
    return [k for k in REQUIRED if b.get(k) is None]


def validate_bill(b: dict, previous: dict | None = None) -> list[dict]:
    missing = missing_required(b)
    if missing:
        return [_flag("E_MISSING", "error", k, f"{k} is missing") for k in missing]

    flags: list[dict] = []

    if b["period_end"] <= b["period_start"]:
        flags.append(_flag("E_PERIOD_ORDER", "error", "period_end",
                           "Present reading date is not after the previous reading date"))

    units = {}
    for name, const in METERS:
        prev, pres, printed = b[f"{name}_prev"], b[f"{name}_present"], b[f"{name}_units_printed"]
        calc = (pres - prev) * b[const]
        units[name] = calc
        if pres < prev:
            flags.append(_flag("E_READING_DECREASED", "error", f"{name}_present",
                               f"{name}: present reading {pres} is lower than previous {prev} "
                               "(misread digit, or meter replaced / rolled over?)"))
        if abs(calc - printed) > TOL:
            flags.append(_flag("E_UNITS_MISMATCH", "error", f"{name}_units_printed",
                               f"{name}: (present - previous) x multiplier = {calc}, but the bill prints {printed}"))

    if b.get("net_import_printed") is not None:
        expected = b["import_units_printed"] - b["export_units_printed"]
        if abs(expected - b["net_import_printed"]) > TOL:
            flags.append(_flag("W_NET_MISMATCH", "warning", "net_import_printed",
                               f"Printed net import {b['net_import_printed']} differs from import - export = {expected}"))

    if units["solar"] + units["import"] - units["export"] < 0:
        flags.append(_flag("W_NEGATIVE_CONSUMPTION", "warning", "export_present",
                           "Calculated total consumption is negative; check export reading"))

    if previous:
        for name, const in METERS:
            if previous.get(f"{name}_present") is not None and b[f"{name}_prev"] != previous[f"{name}_present"]:
                flags.append(_flag("W_PREV_READING_MISMATCH", "warning", f"{name}_prev",
                                   f"{name}: previous reading {b[f'{name}_prev']} differs from last bill's "
                                   f"present reading {previous[f'{name}_present']}"))
        if previous.get("period_end") and previous["period_end"] != b["period_start"]:
            flags.append(_flag("W_PERIOD_GAP", "warning", "period_start",
                               f"Period starts {b['period_start']} but the last bill ended {previous['period_end']}"))
        for const in ("meter_constant", "solar_constant"):
            if previous.get(const) is not None and previous[const] != b[const]:
                flags.append(_flag("W_MULTIPLIER_CHANGED", "warning", const,
                                   f"{const} is {b[const]} but was {previous[const]} last month"))
        if all(previous.get(k) is not None for k in ("solar_present", "solar_prev", "solar_constant")):
            prev_solar = (previous["solar_present"] - previous["solar_prev"]) * previous["solar_constant"]
            if prev_solar > 0 and units["solar"] < prev_solar / 2:
                flags.append(_flag("W_SOLAR_DROP", "warning", "solar_present",
                                   f"Solar generation {units['solar']} is less than half of last month's {prev_solar}"))

    for path in b.get("unclear_fields") or []:
        flags.append(_flag("W_UNCLEAR_FIELD", "warning", path, "Extraction marked this field as unclear; check it against the bill"))

    return flags
