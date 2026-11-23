"""Golden-file tests: verify real extracted bills against faculty answer key and schema."""
import json
from decimal import Decimal
from pathlib import Path

from app.analytics.calculations import monthly_energy
from app.extraction.extractor import _check_shape
from app.extraction.mapping import to_bill_fields
from app.extraction.validate import validate_bill

FIXTURES = Path(__file__).parent / "fixtures"


def test_golden_feb25():
    data = json.loads((FIXTURES / "golden_feb25.json").read_text())
    _check_shape(data)
    conn_f, bill_f = to_bill_fields(data)
    flags = validate_bill(bill_f)
    assert flags == []

    # Formulas check for Feb-25: a 31934, b 68380, c 1568, d 66812, total 98746
    m = monthly_energy(
        solar_prev=bill_f["solar_prev"], solar_present=bill_f["solar_present"], solar_constant=bill_f["solar_constant"],
        import_prev=bill_f["import_prev"], import_present=bill_f["import_present"],
        export_prev=bill_f["export_prev"], export_present=bill_f["export_present"],
        meter_constant=bill_f["meter_constant"]
    )
    assert m.solar_generated == Decimal("31934")
    assert m.imported == Decimal("68380")
    assert m.exported == Decimal("1568")
    assert m.net_energy == Decimal("66812")
    assert m.total_consumed == Decimal("98746")


def test_golden_mar25():
    feb_data = json.loads((FIXTURES / "golden_feb25.json").read_text())
    mar_data = json.loads((FIXTURES / "golden_mar25.json").read_text())
    _check_shape(mar_data)
    _, feb_bill = to_bill_fields(feb_data)
    _, mar_bill = to_bill_fields(mar_data)

    # Validate chaining onto Feb
    flags = validate_bill(mar_bill, previous=feb_bill)
    assert flags == []

    # Mar-25 Answer key: a=37102, b=77196, c=2610, d=74586, total=111688, savings=259714 (at rate 7)
    m = monthly_energy(
        solar_prev=mar_bill["solar_prev"], solar_present=mar_bill["solar_present"], solar_constant=mar_bill["solar_constant"],
        import_prev=mar_bill["import_prev"], import_present=mar_bill["import_present"],
        export_prev=mar_bill["export_prev"], export_present=mar_bill["export_present"],
        meter_constant=mar_bill["meter_constant"],
        rate=Decimal("7")
    )
    assert m.solar_generated == Decimal("37102")
    assert m.imported == Decimal("77196")
    assert m.exported == Decimal("2610")
    assert m.net_energy == Decimal("74586")
    assert m.total_consumed == Decimal("111688")
    assert m.savings == Decimal("259714")
