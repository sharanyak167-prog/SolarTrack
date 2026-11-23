"""Historical backfill module for importing past months from CSV or Excel (.xlsx).

Applies the exact same formulas and validation rules as live uploads.
"""
import csv
from datetime import date, datetime
from decimal import Decimal
import io
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics.calculations import monthly_energy
from .extraction.mapping import parse_month_label
from .extraction.validate import validate_bill
from .models import Bill, BillFile, Connection, MonthlyRate
from .services import month_start, rate_for, set_rate

# Approved default constants
DEFAULT_SOLAR_CONST = Decimal("100")
DEFAULT_METER_CONST = Decimal("2000")
DEFAULT_RR = "KULHT15"


def _dec(v, default=None) -> Optional[Decimal]:
    if v is None or str(v).strip() == "":
        return default
    try:
        return Decimal(str(v).strip().replace(",", ""))
    except Exception:
        return default


def parse_row_date(val: str) -> Optional[date]:
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%b-%y", "%b-%Y", "%B-%Y", "%b %Y", "%B %Y"):
        try:
            d = datetime.strptime(val, fmt)
            return date(d.year, d.month, 1)
        except ValueError:
            continue
    return None


def get_or_create_connection(s: Session, rr_number: str = DEFAULT_RR) -> Connection:
    conn = s.scalar(select(Connection).where(Connection.rr_number == rr_number))
    if not conn:
        conn = Connection(
            rr_number=rr_number,
            consumer_name="THE PRESIDENT, ST JOSEPHS ENG COLLEGE VOMANJOOR MANGALORE",
            account_id="8758488111",
            tariff="HT2C2",
            voltage_class="11kv",
            contract_demand_kva=Decimal("350"),
            meter_constant=DEFAULT_METER_CONST,
            solar_constant=DEFAULT_SOLAR_CONST,
        )
        s.add(conn)
        s.flush()
    return conn


def import_records(s: Session, records: list[dict], user: str = "admin") -> dict:
    """Import and validate records into database.
    
    Each record must have: bill_month, plus either readings or printed units.
    """
    conn = get_or_create_connection(s)
    created_bills = 0
    created_rates = 0
    errors = []

    # Sort records chronologically
    valid_records = []
    for idx, r in enumerate(records, start=1):
        m_date = parse_row_date(r.get("bill_month") or r.get("month") or "")
        if not m_date:
            errors.append(f"Row {idx}: Invalid bill_month '{r.get('bill_month')}'")
            continue
        valid_records.append((m_date, r, idx))

    valid_records.sort(key=lambda x: x[0])

    # Rolling readings state for continuous series when only units are supplied
    last_solar = Decimal("10000.00")
    last_import = Decimal("1000.0000")
    last_export = Decimal("50.0000")

    for m_date, r, row_idx in valid_records:
        solar_const = _dec(r.get("solar_constant"), DEFAULT_SOLAR_CONST)
        meter_const = _dec(r.get("meter_constant"), DEFAULT_METER_CONST)
        rate = _dec(r.get("rate_per_unit") or r.get("rate"))

        # Check readings vs printed units
        sol_units = _dec(r.get("solar_units_printed") or r.get("solar_units") or r.get("solar_generated"))
        imp_units = _dec(r.get("import_units_printed") or r.get("import_units") or r.get("imported"))
        exp_units = _dec(r.get("export_units_printed") or r.get("export_units") or r.get("exported"))

        sol_prev = _dec(r.get("solar_prev"))
        sol_pres = _dec(r.get("solar_present"))
        imp_prev = _dec(r.get("import_prev"))
        imp_pres = _dec(r.get("import_present"))
        exp_prev = _dec(r.get("export_prev"))
        exp_pres = _dec(r.get("export_present"))

        # Synthesize readings if only units provided
        if sol_pres is None or sol_prev is None:
            if sol_units is None:
                errors.append(f"Row {row_idx} ({m_date}): Missing solar generation units or readings")
                continue
            sol_prev = last_solar
            sol_pres = sol_prev + (sol_units / solar_const)
            last_solar = sol_pres
        else:
            sol_units = (sol_pres - sol_prev) * solar_const
            last_solar = sol_pres

        if imp_pres is None or imp_prev is None:
            if imp_units is None:
                errors.append(f"Row {row_idx} ({m_date}): Missing import units or readings")
                continue
            imp_prev = last_import
            imp_pres = imp_prev + (imp_units / meter_const)
            last_import = imp_pres
        else:
            imp_units = (imp_pres - imp_prev) * meter_const
            last_import = imp_pres

        if exp_pres is None or exp_prev is None:
            if exp_units is None:
                exp_units = Decimal("0")
            exp_prev = last_export
            exp_pres = exp_prev + (exp_units / meter_const)
            last_export = exp_pres
        else:
            exp_units = (exp_pres - exp_prev) * meter_const
            last_export = exp_pres

        net_imp = imp_units - exp_units

        # Period dates
        period_start = m_date
        # End date is end of month or start of next
        if m_date.month == 12:
            period_end = date(m_date.year + 1, 1, 1)
        else:
            period_end = date(m_date.year, m_date.month + 1, 1)

        bill_dict = {
            "bill_month": m_date,
            "period_start": period_start,
            "period_end": period_end,
            "meter_constant": meter_const,
            "solar_constant": solar_const,
            "import_prev": imp_prev,
            "import_present": imp_pres,
            "import_units_printed": imp_units,
            "export_prev": exp_prev,
            "export_present": exp_pres,
            "export_units_printed": exp_units,
            "solar_prev": sol_prev,
            "solar_present": sol_pres,
            "solar_units_printed": sol_units,
            "net_import_printed": net_imp,
            "unclear_fields": [],
        }

        flags = validate_bill(bill_dict)
        error_flags = [f for f in flags if f["severity"] == "error"]
        if error_flags:
            errors.append(f"Row {row_idx} ({m_date}) validation error: {error_flags[0]['message']}")
            continue

        # Check existing bill
        existing = s.scalar(select(Bill).where(Bill.connection_id == conn.id, Bill.bill_month == m_date, Bill.is_current.is_(True)))
        if existing:
            # Update existing verified bill
            for k, v in bill_dict.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            existing.status = "verified"
            existing.verified_by = user
            existing.verified_at = datetime.now()
            existing.validation_flags = flags
        else:
            # Create synthetic bill file record
            bf = BillFile(
                original_name=f"backfill_{m_date.strftime('%Y_%m')}.csv",
                stored_path="backfill",
                sha256=f"backfill_{conn.id}_{m_date.isoformat()}",
                mime_type="text/csv",
                uploaded_by=user,
            )
            s.add(bf)
            s.flush()

            bill = Bill(
                connection_id=conn.id,
                file_id=bf.id,
                bill_month=m_date,
                bill_month_label=m_date.strftime("%b-%y"),
                period_start=period_start,
                period_end=period_end,
                bill_date=period_end,
                due_date=period_end,
                meter_constant=meter_const,
                solar_constant=solar_const,
                import_prev=imp_prev,
                import_present=imp_pres,
                import_units_printed=imp_units,
                export_prev=exp_prev,
                export_present=exp_pres,
                export_units_printed=exp_units,
                solar_prev=sol_prev,
                solar_present=sol_pres,
                solar_units_printed=sol_units,
                net_import_printed=net_imp,
                status="verified",
                validation_flags=flags,
                unclear_fields=[],
                extraction_json={"backfill": True, "source": "historical_import"},
                extraction_model="historical-backfill",
                version=1,
                is_current=True,
                verified_by=user,
                verified_at=datetime.now(),
            )
            s.add(bill)
            created_bills += 1

        if rate is not None:
            set_rate(s, conn.id, m_date, rate, user)
            created_rates += 1

    s.commit()
    return {
        "success": True,
        "created_or_updated_bills": created_bills,
        "rates_updated": created_rates,
        "errors": errors,
    }


def parse_csv_content(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    return [row for row in reader]


def parse_excel_content(data: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip().lower() if h else f"col_{i}" for i, h in enumerate(rows[0])]
    records = []
    for r in rows[1:]:
        if not any(r):
            continue
        record = {headers[i]: r[i] for i in range(min(len(headers), len(r)))}
        records.append(record)
    return records
