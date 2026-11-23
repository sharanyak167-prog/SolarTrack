# FORMULAS.md — Approved calculation rules (v1, from faculty note, Mar 2025)

All values come from ONE bill. Previous readings are the "Previous Reading" column
printed on that same bill. No rounding anywhere: keep full precision, round only
when displaying.

## Inputs (per bill)

| Symbol | Source on bill |
|---|---|
| solar_present / solar_prev | Solar Generation Meter, present and previous reading |
| import_present / import_prev | IMPORT ENERGY, Total Consumption (B-1) row |
| export_present / export_prev | SOLAR EXPORT ENERGY, Units row |
| solar_constant | "Solar-Constant" (e.g. 100) |
| meter_constant | "Meter Constant" (e.g. 2000) |
| rate | Savings rate in Rs per unit. Entered by staff for each month. NOT read from the bill and NOT a default (Mar-25 = 7) |

## Formulas

| Line | Name | Formula |
|---|---|---|
| a | Total solar generated (kWh) | (solar_present - solar_prev) x solar_constant |
| b | Energy imported from MESCOM (kWh) | (import_present - import_prev) x meter_constant |
| c | Energy exported to MESCOM (kWh) | (export_present - export_prev) x meter_constant |
| d | Net energy | b - c |
| | Total energy consumed (kWh) | a + d  (= a + b - c) |
| | Savings (Rs) | a x rate  (solar generated only; exports not included) |

Sub-meter consumption on the bill is NOT used in any formula.

## Reports

Monthly summary = the figures above for one bill. Six-monthly and yearly reports are
built from the monthly summaries (confirm with faculty that totals are plain sums).

## Answer key: Mar-25 (from faculty's handwritten note)

| Input | Previous | Present |
|---|---|---|
| Solar | 14107.17 | 14478.19 |
| Import | 1524.2360 | 1562.8340 |
| Export | 75.1480 | 76.4530 |

Constants: solar 100, meter 2000. Rate: 7.

| Result | Value |
|---|---|
| a solar generated | 37,102 |
| b imported | 77,196 |
| c exported | 2,610 |
| d net energy | 74,586 |
| total consumed | 111,688 |
| savings | 259,714 |

## Answer key: Feb-25 (read from the bill; rate not given)

a 31,934 / b 68,380 / c 1,568 / d 66,812 / total 98,746.
