from copy import deepcopy
from datetime import date
from decimal import Decimal as D

from app.extraction.fixtures import FEB_25
from app.extraction.mapping import parse_month_label, to_bill_fields
from app.extraction.validate import validate_bill


def feb():
    return to_bill_fields(deepcopy(FEB_25))[1]


def codes(flags):
    return {f["code"] for f in flags}


def test_mapping_feb_25():
    conn, b = to_bill_fields(FEB_25)
    assert conn["rr_number"] == "KULHT15"
    assert b["bill_month"] == date(2025, 2, 1)
    assert b["period_start"] == date(2025, 2, 1) and b["period_end"] == date(2025, 3, 1)
    assert b["solar_present"] == D("14107.17") and b["import_prev"] == D("1490.0460")
    assert b["meter_constant"] == D(2000) and b["solar_constant"] == D(100)


def test_clean_bill_has_no_flags():
    assert validate_bill(feb()) == []


def test_month_label_formats():
    assert parse_month_label("Feb-25", None) == date(2025, 2, 1)
    assert parse_month_label("Mar-2025", None) == date(2025, 3, 1)
    assert parse_month_label("garbage", date(2025, 4, 17)) == date(2025, 4, 1)


def test_misread_digit_is_an_error():
    b = feb()
    b["import_present"] = D("1524.2960")  # one digit misread
    assert "E_UNITS_MISMATCH" in codes(validate_bill(b))


def test_wrong_multiplier_is_an_error():
    b = feb()
    b["meter_constant"] = D(200)
    assert "E_UNITS_MISMATCH" in codes(validate_bill(b))


def test_decreasing_reading_is_an_error():
    b = feb()
    b["solar_present"], b["solar_prev"] = b["solar_prev"], b["solar_present"]
    assert "E_READING_DECREASED" in codes(validate_bill(b))


def test_missing_field_is_an_error():
    b = feb()
    b["export_present"] = None
    flags = validate_bill(b)
    assert [f["code"] for f in flags] == ["E_MISSING"]


def test_net_mismatch_warning():
    b = feb()
    b["net_import_printed"] = D("60000")
    assert "W_NET_MISMATCH" in codes(validate_bill(b))


def test_continuity_checks_against_previous_bill():
    prev = feb()
    mar = feb()
    mar.update(bill_month=date(2025, 3, 1), period_start=date(2025, 3, 1), period_end=date(2025, 4, 1),
               solar_prev=D("14107.17"), solar_present=D("14478.19"), solar_units_printed=D(37102),
               import_prev=D("1524.2360"), import_present=D("1562.8340"), import_units_printed=D(77196),
               export_prev=D("75.1480"), export_present=D("76.4530"), export_units_printed=D(2610),
               net_import_printed=D(74586))
    assert validate_bill(mar, prev) == []          # March from sir's note chains cleanly onto Feb

    gap = dict(mar, period_start=date(2025, 3, 5), period_end=date(2025, 4, 5))
    assert "W_PERIOD_GAP" in codes(validate_bill(gap, prev))

    jump = dict(mar, import_prev=D("1500.0000"), import_units_printed=D(125668))
    assert "W_PREV_READING_MISMATCH" in codes(validate_bill(jump, prev))


def test_solar_drop_warning():
    prev = feb()
    low = dict(prev, bill_month=date(2025, 3, 1), period_start=date(2025, 3, 1), period_end=date(2025, 4, 1),
               solar_prev=D("14107.17"), solar_present=D("14127.17"), solar_units_printed=D(2000),
               import_prev=D("1524.2360"), import_present=D("1560.0000"), import_units_printed=D("71528"),
               export_prev=D("75.1480"), export_present=D("75.1480"), export_units_printed=D(0),
               net_import_printed=None)
    assert "W_SOLAR_DROP" in codes(validate_bill(low, prev))


def test_unclear_fields_are_flagged():
    b = feb()
    b["unclear_fields"] = ["meters.solar_generation.present_reading"]
    assert "W_UNCLEAR_FIELD" in codes(validate_bill(b))
