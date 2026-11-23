"""Business logic: ingest, edit, verify, stats. Routes in main.py stay thin."""
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .analytics.calculations import MonthlyEnergy, aggregate, monthly_energy
from .extraction import extractor
from .extraction.mapping import to_bill_fields
from .extraction.validate import missing_required, validate_bill
from .models import AuditLog, Bill, BillFile, Connection, MonthlyRate

FLAT_KEYS = [
    "bill_month", "period_start", "period_end", "meter_constant", "solar_constant",
    "import_prev", "import_present", "import_units_printed",
    "export_prev", "export_present", "export_units_printed",
    "solar_prev", "solar_present", "solar_units_printed",
    "net_import_printed", "net_export_printed", "unclear_fields",
]


def month_start(d: date) -> date:
    return d.replace(day=1)


def flat(bill: Bill) -> dict:
    return {k: getattr(bill, k) for k in FLAT_KEYS}


def audit(s: Session, bill_id: Optional[int], user: str, action: str,
          field: Optional[str] = None, old=None, new=None) -> None:
    s.add(AuditLog(bill_id=bill_id, user=user, action=action, field_name=field,
                   old_value=None if old is None else str(old),
                   new_value=None if new is None else str(new)))


def previous_bill(s: Session, bill: Bill) -> Optional[Bill]:
    return s.scalars(
        select(Bill).where(Bill.connection_id == bill.connection_id, Bill.bill_month < bill.bill_month,
                           Bill.is_current.is_(True), Bill.status != "rejected")
        .order_by(Bill.bill_month.desc())).first()


def revalidate(s: Session, bill: Bill) -> None:
    prev = previous_bill(s, bill)
    bill.validation_flags = validate_bill(flat(bill), flat(prev) if prev else None)
    if bill.status != "verified":
        bill.status = "needs_review" if bill.validation_flags else "extracted"


def rate_for(s: Session, connection_id: int, bill_month: date) -> Optional[Decimal]:
    r = s.scalar(select(MonthlyRate).where(MonthlyRate.connection_id == connection_id,
                                           MonthlyRate.bill_month == bill_month))
    return r.rate_per_unit if r else None


def energy_for(bill: Bill, rate: Optional[Decimal]) -> MonthlyEnergy:
    return monthly_energy(
        solar_prev=bill.solar_prev, solar_present=bill.solar_present, solar_constant=bill.solar_constant,
        import_prev=bill.import_prev, import_present=bill.import_present,
        export_prev=bill.export_prev, export_present=bill.export_present,
        meter_constant=bill.meter_constant, rate=rate)


def get_bill_or_404(s: Session, bill_id: int) -> Bill:
    bill = s.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    return bill


def ingest_upload(s: Session, *, filename: str, data: bytes, user: str, replace: bool = False, page_num: Optional[int] = None) -> Bill:
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Use PDF, PNG or JPG.")
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 15 MB")

    digest = sha256(data).hexdigest()
    dup = s.scalar(select(BillFile).where(BillFile.sha256 == digest))
    if dup:
        existing = s.scalar(select(Bill).where(Bill.file_id == dup.id))
        raise HTTPException(409, {"message": "This exact file was already uploaded",
                                  "existing_bill_id": existing.id if existing else None})

    folder = config.upload_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}{ext}"
    path.write_bytes(data)

    def fail(code: int, detail):
        path.unlink(missing_ok=True)
        raise HTTPException(code, detail)

    try:
        if page_num is not None:
            extracted = extractor.extract_bill(str(path), page_num=page_num)
        else:
            extracted = extractor.extract_bill(str(path))
    except extractor.ExtractionError as e:
        fail(422, str(e))

    conn_f, bill_f = to_bill_fields(extracted)
    if not conn_f["rr_number"]:
        fail(422, "Could not read the RR number from the bill")

    conn = s.scalar(select(Connection).where(Connection.rr_number == conn_f["rr_number"]))
    for k in ("meter_constant", "solar_constant"):
        if bill_f[k] is None and conn:
            bill_f[k] = getattr(conn, k)
    missing = missing_required(bill_f)
    if missing:
        fail(422, {"message": "Could not read these required fields; try a clearer file or enter them manually",
                   "missing": missing})

    if not conn:
        conn = Connection(**{k: v for k, v in conn_f.items()})
        conn.meter_constant, conn.solar_constant = bill_f["meter_constant"], bill_f["solar_constant"]
        s.add(conn)
        s.flush()

    existing = s.scalar(select(Bill).where(Bill.connection_id == conn.id, Bill.bill_month == bill_f["bill_month"],
                                           Bill.is_current.is_(True)))
    if existing and existing.status == "verified" and not replace:
        fail(409, {"message": "A verified bill already exists for this month. Upload with replace=true to supersede it.",
                   "existing_bill_id": existing.id})

    bf = BillFile(original_name=filename, stored_path=str(path), sha256=digest,
                  mime_type=config.ALLOWED_TYPES[ext], uploaded_by=user)
    s.add(bf)
    s.flush()

    top_version = s.scalar(select(Bill.version).where(Bill.connection_id == conn.id, Bill.bill_month == bill_f["bill_month"])
                           .order_by(Bill.version.desc())) or 0
    if existing:
        existing.is_current = False

    bill = Bill(connection_id=conn.id, file_id=bf.id, extraction_json=extracted,
                extraction_model="mock-fixture" if config.extraction_mode() == "mock" else config.gemini_model(),
                version=top_version + 1, status="extracted", **bill_f)
    s.add(bill)
    s.flush()
    revalidate(s, bill)
    audit(s, bill.id, user, "upload", "file", None, filename)
    s.commit()
    return bill


def edit_bill(s: Session, bill: Bill, changes: dict, user: str) -> Bill:
    if bill.status == "rejected":
        raise HTTPException(409, "Rejected bills cannot be edited")
    if "bill_month" in changes:
        changes["bill_month"] = month_start(changes["bill_month"])
        clash = s.scalar(select(Bill).where(Bill.connection_id == bill.connection_id, Bill.bill_month == changes["bill_month"],
                                            Bill.is_current.is_(True), Bill.id != bill.id))
        if clash:
            raise HTTPException(409, f"Bill {clash.id} already covers that month")
    changed = False
    for field, new in changes.items():
        old = getattr(bill, field)
        if old != new:
            audit(s, bill.id, user, "edit", field, old, new)
            setattr(bill, field, new)
            changed = True
    if changed:
        bill.status, bill.verified_by, bill.verified_at = "needs_review", None, None
        revalidate(s, bill)
    s.commit()
    return bill


def verify_bill(s: Session, bill: Bill, user: str) -> Bill:
    if bill.status == "rejected":
        raise HTTPException(409, "Rejected bills cannot be verified")
    revalidate(s, bill)
    errors = [f for f in bill.validation_flags if f["severity"] == "error"]
    if errors:
        raise HTTPException(409, {"message": "Fix these errors before verifying", "errors": errors})
    bill.status, bill.verified_by, bill.verified_at = "verified", user, datetime.now(timezone.utc).replace(tzinfo=None)
    audit(s, bill.id, user, "verify")
    s.commit()
    return bill


def reject_bill(s: Session, bill: Bill, user: str) -> Bill:
    bill.status, bill.verified_by, bill.verified_at = "rejected", None, None
    audit(s, bill.id, user, "reject")
    s.commit()
    return bill


def set_rate(s: Session, connection_id: int, bill_month: date, rate: Decimal, user: str) -> MonthlyRate:
    if not s.get(Connection, connection_id):
        raise HTTPException(404, "Connection not found")
    if rate < 0:
        raise HTTPException(422, "Rate cannot be negative")
    month = month_start(bill_month)
    r = s.scalar(select(MonthlyRate).where(MonthlyRate.connection_id == connection_id, MonthlyRate.bill_month == month))
    if r:
        audit(s, None, user, "rate_change", f"{connection_id}:{month}", r.rate_per_unit, rate)
        r.rate_per_unit, r.entered_by = rate, user
    else:
        r = MonthlyRate(connection_id=connection_id, bill_month=month, rate_per_unit=rate, entered_by=user)
        s.add(r)
        audit(s, None, user, "rate_set", f"{connection_id}:{month}", None, rate)
    s.commit()
    return r


def verified_bills(s: Session, connection_id: int, start: Optional[date] = None, end: Optional[date] = None) -> list[Bill]:
    q = select(Bill).where(Bill.connection_id == connection_id, Bill.is_current.is_(True), Bill.status == "verified")
    if start:
        q = q.where(Bill.bill_month >= month_start(start))
    if end:
        q = q.where(Bill.bill_month <= month_start(end))
    return list(s.scalars(q.order_by(Bill.bill_month)))


def months_between(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def delete_bill(s: Session, bill: Bill, user: str) -> None:
    audit(s, bill.id, user, "delete", None, None, f"bill_month={bill.bill_month}")
    s.delete(bill)
    s.commit()


def get_cumulative_stats(s: Session, connection_id: int, up_to_month: date) -> dict:
    """Calculate cumulative generation and savings from inception to given month."""
    bills = list(s.scalars(
        select(Bill).where(
            Bill.connection_id == connection_id,
            Bill.is_current.is_(True),
            Bill.status == "verified",
            Bill.bill_month <= month_start(up_to_month)
        ).order_by(Bill.bill_month)
    ))
    tot_solar = Decimal(0)
    tot_savings = Decimal(0)
    has_savings = True

    for b in bills:
        rate = rate_for(s, connection_id, b.bill_month)
        e = energy_for(b, rate)
        tot_solar += e.solar_generated
        if e.savings is not None:
            tot_savings += e.savings
        else:
            has_savings = False

    return {
        "total_units": tot_solar,
        "total_savings": tot_savings if has_savings else None,
        "months_count": len(bills),
    }


def summary(s: Session, connection_id: int, start: date, end: date) -> dict:
    start, end = month_start(start), month_start(end)
    if end < start:
        raise HTTPException(422, "end is before start")
    bills = verified_bills(s, connection_id, start, end)
    have = {b.bill_month for b in bills}
    rows, missing_rates = [], []
    for b in bills:
        rate = rate_for(s, connection_id, b.bill_month)
        if rate is None:
            missing_rates.append(b.bill_month)
        rows.append(energy_for(b, rate))
    total = aggregate(rows) if rows else MonthlyEnergy(*(Decimal(0),) * 5, savings=None)
    return {"connection_id": connection_id, "start": start, "end": end, "months_included": len(rows),
            "missing_months": [m for m in months_between(start, end) if m not in have],
            "missing_rates": missing_rates, "total": asdict(total)}
