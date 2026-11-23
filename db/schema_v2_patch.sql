-- Patch for schema.sql (v1 -> v2): savings rate is entered per month, never defaulted.
USE solar_monitor;

CREATE TABLE monthly_rates (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  connection_id   INT NOT NULL,
  bill_month      DATE NOT NULL,                 -- first day of month, e.g. 2025-03-01
  rate_per_unit   DECIMAL(8,4) NOT NULL,         -- Rs per kWh used for savings (Mar-25 = 7)
  entered_by      INT NOT NULL,
  entered_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_rate (connection_id, bill_month),
  FOREIGN KEY (connection_id) REFERENCES connections(id),
  FOREIGN KEY (entered_by)    REFERENCES users(id)
);

-- Replaces v_monthly_energy: sir's formulas, no rounding, savings = solar * monthly rate.
-- savings_rs is NULL until staff enter that month's rate.
DROP VIEW IF EXISTS v_monthly_energy;
CREATE VIEW v_monthly_energy AS
SELECT
  b.connection_id,
  b.bill_month,
  b.period_start,
  b.period_end,
  (b.solar_present  - b.solar_prev)  * b.solar_constant AS solar_generated_kwh,   -- a
  (b.import_present - b.import_prev) * b.meter_constant AS imported_kwh,          -- b
  (b.export_present - b.export_prev) * b.meter_constant AS exported_kwh,          -- c
  (b.import_present - b.import_prev) * b.meter_constant
    - (b.export_present - b.export_prev) * b.meter_constant AS net_energy_kwh,    -- d = b - c
  (b.solar_present  - b.solar_prev)  * b.solar_constant
    + (b.import_present - b.import_prev) * b.meter_constant
    - (b.export_present - b.export_prev) * b.meter_constant AS total_consumed_kwh, -- a + d
  (b.solar_present  - b.solar_prev)  * b.solar_constant * r.rate_per_unit AS savings_rs
FROM bills b
LEFT JOIN monthly_rates r
  ON r.connection_id = b.connection_id AND r.bill_month = b.bill_month
WHERE b.is_current = 1 AND b.status = 'verified';
