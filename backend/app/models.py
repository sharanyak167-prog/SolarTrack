"""Database models. Mirrors db/schema.sql + db/schema_v2_patch.sql."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer,
                        Numeric, String, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


READING = Numeric(14, 4, asdecimal=True)
UNITS = Numeric(14, 2, asdecimal=True)
CONST = Numeric(10, 2, asdecimal=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    rr_number: Mapped[str] = mapped_column(String(30), unique=True)
    account_id: Mapped[Optional[str]] = mapped_column(String(30))
    consumer_name: Mapped[Optional[str]] = mapped_column(String(255))
    tariff: Mapped[Optional[str]] = mapped_column(String(20))
    voltage_class: Mapped[Optional[str]] = mapped_column(String(20))
    contract_demand_kva: Mapped[Optional[Decimal]] = mapped_column(CONST)
    meter_constant: Mapped[Decimal] = mapped_column(CONST)
    solar_constant: Mapped[Decimal] = mapped_column(CONST)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillFile(Base):
    __tablename__ = "bill_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    uploaded_by: Mapped[str] = mapped_column(String(60), default="anonymous")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("connection_id", "bill_month", "version", name="uq_bill_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("bill_files.id"))
    page_used: Mapped[int] = mapped_column(Integer, default=1)

    bill_month: Mapped[date] = mapped_column(Date)
    bill_month_label: Mapped[Optional[str]] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    bill_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date)

    meter_constant: Mapped[Decimal] = mapped_column(CONST)
    solar_constant: Mapped[Decimal] = mapped_column(CONST)

    import_prev: Mapped[Decimal] = mapped_column(READING)
    import_present: Mapped[Decimal] = mapped_column(READING)
    import_units_printed: Mapped[Decimal] = mapped_column(UNITS)
    export_prev: Mapped[Decimal] = mapped_column(READING)
    export_present: Mapped[Decimal] = mapped_column(READING)
    export_units_printed: Mapped[Decimal] = mapped_column(UNITS)
    solar_prev: Mapped[Decimal] = mapped_column(READING)
    solar_present: Mapped[Decimal] = mapped_column(READING)
    solar_units_printed: Mapped[Decimal] = mapped_column(UNITS)

    net_import_printed: Mapped[Optional[Decimal]] = mapped_column(UNITS)
    net_export_printed: Mapped[Optional[Decimal]] = mapped_column(UNITS)
    sub_meter_units: Mapped[Optional[Decimal]] = mapped_column(UNITS)
    recorded_demand_kva: Mapped[Optional[Decimal]] = mapped_column(CONST)
    power_factor: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2, asdecimal=True))
    kvah_raw: Mapped[Optional[list]] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(20), default="extracted")  # extracted|needs_review|verified|rejected
    validation_flags: Mapped[Optional[list]] = mapped_column(JSON)
    unclear_fields: Mapped[Optional[list]] = mapped_column(JSON)
    extraction_json: Mapped[dict] = mapped_column(JSON)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    verified_by: Mapped[Optional[str]] = mapped_column(String(60))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MonthlyRate(Base):
    """Savings rate (Rs per kWh), entered by staff for each month. Never defaulted."""
    __tablename__ = "monthly_rates"
    __table_args__ = (UniqueConstraint("connection_id", "bill_month", name="uq_rate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id"))
    bill_month: Mapped[date] = mapped_column(Date)
    rate_per_unit: Mapped[Decimal] = mapped_column(Numeric(8, 4, asdecimal=True))
    entered_by: Mapped[str] = mapped_column(String(60), default="anonymous")
    entered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bills.id"))
    user: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(40))
    field_name: Mapped[Optional[str]] = mapped_column(String(60))
    old_value: Mapped[Optional[str]] = mapped_column(String(255))
    new_value: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
