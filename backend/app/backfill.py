"""Import source readings, never synthesized readings or automatically verified bills."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Bill, BillFile, Connection
from .services import audit, revalidate, set_rate


def parse_row_date(value):
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def parse_csv_content(content: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))


def parse_excel_content(data: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        rows = wb.active.iter_rows(values_only=True)
        headers = [str(h).strip().lower() if h else '' for h in next(rows, ())]
        return [dict(zip(headers, row)) for row in rows if any(v is not None for v in row)]
    finally:
        wb.close()


def import_records(s: Session, records: list[dict], user: str = "admin") -> dict:
    created, rates, errors = 0, 0, []
    numeric = ["solar_prev", "solar_present", "solar_units_printed", "import_prev", "import_present", "import_units_printed", "export_prev", "export_present", "export_units_printed", "solar_constant", "meter_constant"]
    for rownum, row in enumerate(records, 2):
        try:
            dates = {k: parse_row_date(row.get(k)) for k in ("bill_month", "period_start", "period_end")}
            if not all(dates.values()):
                raise ValueError("bill_month, period_start and period_end must be ISO dates")
            dates['bill_month'] = dates['bill_month'].replace(day=1)
            rr = str(row.get('rr_number') or '').strip()
            if not rr or len(rr) > 30:
                raise ValueError("rr_number is required (maximum 30 characters)")
            values = {}
            for name in numeric:
                val = Decimal(str(row.get(name) or '').strip())
                if not val.is_finite() or val < 0:
                    raise ValueError(f"{name} must be a finite non-negative number")
                values[name] = val
            if not values['solar_constant'] or not values['meter_constant']:
                raise ValueError("multipliers must be positive")
            net = row.get('net_import_printed')
            if net is not None and str(net).strip():
                values['net_import_printed'] = Decimal(str(net).strip())
                if not values['net_import_printed'].is_finite():
                    raise ValueError('net_import_printed must be finite')
            rate = row.get('rate_per_unit')
            rate = Decimal(str(rate).strip()) if rate is not None and str(rate).strip() else None
            if rate is not None and (not rate.is_finite() or rate < 0):
                raise ValueError('rate_per_unit must be finite and non-negative')
            conn = s.scalar(select(Connection).where(Connection.rr_number == rr))
            if conn is None:
                conn = Connection(rr_number=rr, solar_constant=values['solar_constant'], meter_constant=values['meter_constant'])
                s.add(conn)
                s.flush()
            existing = s.scalar(select(Bill.id).where(Bill.connection_id == conn.id, Bill.bill_month == dates['bill_month'], Bill.is_current.is_(True)))
            if existing:
                raise ValueError('a current bill already exists; review it instead of overwriting it')
            bf = BillFile(original_name=f"backfill_{dates['bill_month']}.csv", stored_path="", sha256=__import__('hashlib').sha256(f"backfill:{rr}:{dates['bill_month']}".encode()).hexdigest(), mime_type="text/csv", uploaded_by=user)
            s.add(bf)
            s.flush()
            bill = Bill(connection_id=conn.id, file_id=bf.id, **dates, **values, status='needs_review', validation_flags=[], unclear_fields=[], extraction_json={'backfill': True}, extraction_model='historical-backfill', version=1, is_current=True)
            s.add(bill)
            s.flush()
            revalidate(s, bill)
            bill.status = 'needs_review'  # Human review is mandatory even with no flags.
            audit(s, bill.id, user, 'backfill_import')
            s.commit()
            created += 1
            if rate is not None:
                set_rate(s, conn.id, dates['bill_month'], rate, user)
                rates += 1
        except (ValueError, InvalidOperation, TypeError) as exc:
            s.rollback()
            errors.append(f"Row {rownum}: {exc}")
    return {'success': not errors, 'created_or_updated_bills': created, 'rates_updated': rates, 'errors': errors}
