"""Historical imports must retain real readings and require review."""
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select
from app import db
from app.backfill import import_records, parse_csv_content
from app.models import Bill

@pytest.fixture
def db_session(tmp_path):
    db.init_db(f"sqlite:///{tmp_path / 'test.db'}")
    with db.SessionLocal() as s:
        yield s

CSV = """bill_month,period_start,period_end,rr_number,solar_prev,solar_present,solar_units_printed,import_prev,import_present,import_units_printed,export_prev,export_present,export_units_printed,solar_constant,meter_constant,net_import_printed,rate_per_unit
2025-03-01,2025-03-01,2025-04-01,TEST,14107.17,14478.19,37102,1524.2360,1562.8340,77196,75.1480,76.4530,2610,100,2000,74586,7
"""

def test_backfill_requires_review(db_session):
    result = import_records(db_session, parse_csv_content(CSV), user="tester")
    assert result['errors'] == []
    bill = db_session.scalar(select(Bill))
    assert bill.status == 'needs_review' and bill.verified_by is None
    assert bill.solar_prev == Decimal('14107.17')
    assert import_records(db_session, parse_csv_content(CSV))['errors']

def test_backfill_rejects_missing_readings(db_session):
    result = import_records(db_session, [{'bill_month': '2025-03-01', 'solar_units_printed': '37102'}])
    assert result['errors'] and db_session.scalar(select(Bill)) is None
