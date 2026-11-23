"""Energy calculations. Rules are in docs/FORMULAS.md.

Decimal is used throughout so there is no floating-point drift and no rounding.
Pass readings as strings or Decimals (e.g. "14478.19"), never floats.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union

Num = Union[str, int, Decimal]


def _d(x: Num) -> Decimal:
    if isinstance(x, float):
        raise TypeError("Pass readings as str or Decimal, not float")
    return Decimal(x)


@dataclass(frozen=True)
class MonthlyEnergy:
    solar_generated: Decimal   # a
    imported: Decimal          # b
    exported: Decimal          # c
    net_energy: Decimal        # d = b - c
    total_consumed: Decimal    # a + d
    savings: Optional[Decimal]  # a * rate; None if no rate entered for the month


def monthly_energy(
    *,
    solar_prev: Num, solar_present: Num, solar_constant: Num,
    import_prev: Num, import_present: Num,
    export_prev: Num, export_present: Num, meter_constant: Num,
    rate: Optional[Num] = None,
) -> MonthlyEnergy:
    a = (_d(solar_present) - _d(solar_prev)) * _d(solar_constant)
    b = (_d(import_present) - _d(import_prev)) * _d(meter_constant)
    c = (_d(export_present) - _d(export_prev)) * _d(meter_constant)
    d = b - c
    return MonthlyEnergy(
        solar_generated=a,
        imported=b,
        exported=c,
        net_energy=d,
        total_consumed=a + d,
        savings=None if rate is None else a * _d(rate),
    )


def aggregate(months: list[MonthlyEnergy]) -> MonthlyEnergy:
    """Plain sums for six-monthly / yearly reports (pending faculty confirmation).
    Savings is None if any month has no rate."""
    savings = None if any(m.savings is None for m in months) else sum(
        (m.savings for m in months), Decimal(0))
    return MonthlyEnergy(
        solar_generated=sum((m.solar_generated for m in months), Decimal(0)),
        imported=sum((m.imported for m in months), Decimal(0)),
        exported=sum((m.exported for m in months), Decimal(0)),
        net_energy=sum((m.net_energy for m in months), Decimal(0)),
        total_consumed=sum((m.total_consumed for m in months), Decimal(0)),
        savings=savings,
    )
