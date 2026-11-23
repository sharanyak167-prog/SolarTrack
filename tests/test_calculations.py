import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.analytics.calculations import aggregate, monthly_energy  # noqa: E402

MAR = dict(
    solar_prev="14107.17", solar_present="14478.19", solar_constant=100,
    import_prev="1524.2360", import_present="1562.8340",
    export_prev="75.1480", export_present="76.4530", meter_constant=2000,
)
FEB = dict(
    solar_prev="13787.83", solar_present="14107.17", solar_constant=100,
    import_prev="1490.0460", import_present="1524.2360",
    export_prev="74.3640", export_present="75.1480", meter_constant=2000,
)


def test_mar_2025_matches_faculty_note():
    r = monthly_energy(**MAR, rate=7)
    assert r.solar_generated == Decimal(37102)
    assert r.imported == Decimal(77196)
    assert r.exported == Decimal(2610)
    assert r.net_energy == Decimal(74586)
    assert r.total_consumed == Decimal(111688)
    assert r.savings == Decimal(259714)


def test_feb_2025_matches_bill():
    r = monthly_energy(**FEB)
    assert r.solar_generated == Decimal(31934)
    assert r.imported == Decimal(68380)
    assert r.exported == Decimal(1568)
    assert r.net_energy == Decimal(66812)
    assert r.total_consumed == Decimal(98746)
    assert r.savings is None  # no rate entered


def test_no_rounding():
    r = monthly_energy(**{**MAR, "solar_present": "14478.1937"}, rate="7.5")
    assert r.solar_generated == (Decimal("14478.1937") - Decimal("14107.17")) * 100


def test_rate_changes_per_month():
    assert monthly_energy(**MAR, rate=7).savings == Decimal(259714)
    assert monthly_energy(**MAR, rate="8.1").savings == Decimal("37102") * Decimal("8.1")


def test_aggregate_sums_months():
    t = aggregate([monthly_energy(**FEB, rate=7), monthly_energy(**MAR, rate=7)])
    assert t.solar_generated == Decimal(31934 + 37102)
    assert t.total_consumed == Decimal(98746 + 111688)
    assert t.savings == Decimal(7 * (31934 + 37102))
    assert aggregate([monthly_energy(**FEB), monthly_energy(**MAR, rate=7)]).savings is None
