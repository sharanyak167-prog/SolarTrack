from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EnergyOut(BaseModel):
    """Formulas in docs/FORMULAS.md. Decimals are sent as exact strings."""
    solar_generated: Decimal   # a
    imported: Decimal          # b
    exported: Decimal          # c
    net_energy: Decimal        # d = b - c
    total_consumed: Decimal    # a + d
    savings: Optional[Decimal] = None  # a x rate; null until the month's rate is entered


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    connection_id: int
    file_id: int
    page_used: int
    bill_month: date
    bill_month_label: Optional[str] = None
    period_start: date
    period_end: date
    bill_date: Optional[date] = None
    due_date: Optional[date] = None
    meter_constant: Decimal
    solar_constant: Decimal
    import_prev: Decimal
    import_present: Decimal
    import_units_printed: Decimal
    export_prev: Decimal
    export_present: Decimal
    export_units_printed: Decimal
    solar_prev: Decimal
    solar_present: Decimal
    solar_units_printed: Decimal
    net_import_printed: Optional[Decimal] = None
    net_export_printed: Optional[Decimal] = None
    sub_meter_units: Optional[Decimal] = None
    recorded_demand_kva: Optional[Decimal] = None
    power_factor: Optional[Decimal] = None
    kvah_raw: Optional[list] = None
    status: str
    validation_flags: list = []
    unclear_fields: list = []
    extraction_model: Optional[str] = None
    version: int
    is_current: bool
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    rate_per_unit: Optional[Decimal] = None
    energy: Optional[EnergyOut] = None


class BillEdit(BaseModel):
    """Fields a reviewer may correct. Only the fields sent are changed."""
    model_config = ConfigDict(extra="forbid")
    bill_month: Optional[date] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    meter_constant: Optional[Decimal] = None
    solar_constant: Optional[Decimal] = None
    import_prev: Optional[Decimal] = None
    import_present: Optional[Decimal] = None
    import_units_printed: Optional[Decimal] = None
    export_prev: Optional[Decimal] = None
    export_present: Optional[Decimal] = None
    export_units_printed: Optional[Decimal] = None
    solar_prev: Optional[Decimal] = None
    solar_present: Optional[Decimal] = None
    solar_units_printed: Optional[Decimal] = None
    net_import_printed: Optional[Decimal] = None
    sub_meter_units: Optional[Decimal] = None


class RateIn(BaseModel):
    connection_id: int
    bill_month: date          # any day in the month; stored as the 1st
    rate_per_unit: Decimal


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    connection_id: int
    bill_month: date
    rate_per_unit: Decimal


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rr_number: str
    account_id: Optional[str] = None
    consumer_name: Optional[str] = None
    tariff: Optional[str] = None
    meter_constant: Decimal
    solar_constant: Decimal


class MonthRow(BaseModel):
    bill_id: int
    bill_month: date
    rate_per_unit: Optional[Decimal] = None
    energy: EnergyOut


class SummaryOut(BaseModel):
    connection_id: int
    start: date
    end: date
    months_included: int
    missing_months: list[date]   # months in range with no verified bill
    missing_rates: list[date]    # included months with no savings rate entered
    total: EnergyOut
