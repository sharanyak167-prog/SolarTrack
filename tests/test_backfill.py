"""Tests for historical backfill via CSV and Excel."""
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.backfill import import_records, parse_csv_content
from app import db
from app.main import create_app
from app.models import Bill, MonthlyRate

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "historical_records_2021_2026.csv"


@pytest.fixture
def db_session(tmp_path):
    url = f"sqlite:///{tmp_path / 'test_backfill.db'}"
    db.init_db(url)
    with db.SessionLocal() as s:
        yield s


def test_import_records_from_csv(db_session):
    records = parse_csv_content(CSV_PATH.read_text(encoding="utf-8"))
    assert len(records) >= 60

    res = import_records(db_session, records, user="tester")
    assert res["success"] is True
    assert res["errors"] == []
    assert res["created_or_updated_bills"] >= 60
    assert res["rates_updated"] >= 60

    # Verify first month: March 2021
    from sqlalchemy import select
    from datetime import date
    mar_21 = db_session.scalar(select(Bill).where(Bill.bill_month == date(2021, 3, 1), Bill.is_current.is_(True)))
    assert mar_21 is not None
    assert mar_21.solar_units_printed == Decimal("13053")
    assert mar_21.import_units_printed == Decimal("25140")
    assert mar_21.export_units_printed == Decimal("1728")
    assert mar_21.status == "verified"

    # Verify rate for March 2021 = 8.05
    rate = db_session.scalar(select(MonthlyRate).where(MonthlyRate.bill_month == date(2021, 3, 1)))
    assert rate is not None
    assert rate.rate_per_unit == Decimal("8.05")
