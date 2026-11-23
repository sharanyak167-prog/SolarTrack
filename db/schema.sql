-- =====================================================================
-- SolarTrack Database Schema for MySQL 8.0+
-- Source of Truth: app.models (SQLAlchemy Declarative Base)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS solar_monitor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE solar_monitor;

-- 1. Users Table (RBAC: admin | viewer)
CREATE TABLE IF NOT EXISTS users (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  username        VARCHAR(60) NOT NULL UNIQUE,
  hashed_password VARCHAR(255) NOT NULL,
  full_name       VARCHAR(100),
  role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
  is_active       BOOLEAN NOT NULL DEFAULT 1,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_users_username (username)
) ENGINE=InnoDB;

-- Default Users Seed (Password: admin123, viewer123)
-- Replace with custom passwords in production.
INSERT IGNORE INTO users (username, hashed_password, full_name, role, is_active)
VALUES 
  ('admin', '$2b$12$tiyGIcz5BDaA52dmXFS3SuOzelGzzopgZtHQFGLYkwk4OBetAZtEa', 'College Administrator', 'admin', 1),
  ('viewer', '$2b$12$0h.1FhZ1N8N6K1q0zXhGPeW1gD8yI5F/pG7R2C5wL9Q4eM0sB1i6a', 'Staff Viewer', 'viewer', 1);

-- 2. Connections Table (MESCOM HT Installation)
CREATE TABLE IF NOT EXISTS connections (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  rr_number           VARCHAR(30) NOT NULL UNIQUE,
  account_id          VARCHAR(30),
  consumer_name       VARCHAR(255),
  tariff              VARCHAR(20),
  voltage_class       VARCHAR(20),
  contract_demand_kva DECIMAL(10,2),
  meter_constant      DECIMAL(10,2) NOT NULL,
  solar_constant      DECIMAL(10,2) NOT NULL,
  created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 3. Bill Files Table (Document storage & SHA-256 deduplication)
CREATE TABLE IF NOT EXISTS bill_files (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  original_name VARCHAR(255) NOT NULL,
  stored_path   VARCHAR(500) NOT NULL,
  sha256        VARCHAR(64) NOT NULL UNIQUE,
  mime_type     VARCHAR(80) NOT NULL,
  uploaded_by   VARCHAR(60) NOT NULL DEFAULT 'anonymous',
  uploaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_files_sha (sha256)
) ENGINE=InnoDB;

-- 4. Bills Table (Extracted & verified monthly energy metrics)
CREATE TABLE IF NOT EXISTS bills (
  id                    INT AUTO_INCREMENT PRIMARY KEY,
  connection_id         INT NOT NULL,
  file_id               INT NOT NULL,
  page_used             INT NOT NULL DEFAULT 1,
  bill_month            DATE NOT NULL,
  bill_month_label      VARCHAR(10),
  period_start          DATE NOT NULL,
  period_end            DATE NOT NULL,
  bill_date             DATE,
  due_date              DATE,
  meter_constant        DECIMAL(10,2) NOT NULL,
  solar_constant        DECIMAL(10,2) NOT NULL,
  import_prev           DECIMAL(14,4) NOT NULL,
  import_present        DECIMAL(14,4) NOT NULL,
  import_units_printed  DECIMAL(14,2) NOT NULL,
  export_prev           DECIMAL(14,4) NOT NULL,
  export_present        DECIMAL(14,4) NOT NULL,
  export_units_printed  DECIMAL(14,2) NOT NULL,
  solar_prev            DECIMAL(14,4) NOT NULL,
  solar_present         DECIMAL(14,4) NOT NULL,
  solar_units_printed   DECIMAL(14,2) NOT NULL,
  net_import_printed    DECIMAL(14,2),
  net_export_printed    DECIMAL(14,2),
  sub_meter_units       DECIMAL(14,2),
  recorded_demand_kva   DECIMAL(10,2),
  power_factor          DECIMAL(4,2),
  kvah_raw              JSON,
  status                VARCHAR(20) NOT NULL DEFAULT 'extracted',
  validation_flags      JSON,
  unclear_fields        JSON,
  extraction_json       JSON NOT NULL,
  extraction_model      VARCHAR(60),
  version               INT NOT NULL DEFAULT 1,
  is_current            BOOLEAN NOT NULL DEFAULT 1,
  verified_by           VARCHAR(60),
  verified_at           DATETIME,
  created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bill_version (connection_id, bill_month, version),
  FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id)       REFERENCES bill_files(id) ON DELETE CASCADE,
  INDEX idx_bills_month (bill_month),
  INDEX idx_bills_status (status)
) ENGINE=InnoDB;

-- 5. Monthly Savings Rates Table (Entered per month, never defaulted)
CREATE TABLE IF NOT EXISTS monthly_rates (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  connection_id   INT NOT NULL,
  bill_month      DATE NOT NULL,
  rate_per_unit   DECIMAL(8,4) NOT NULL,
  entered_by      VARCHAR(60) NOT NULL DEFAULT 'anonymous',
  entered_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_rate (connection_id, bill_month),
  FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 6. Audit Log Table (Full traceability of edits and verifications)
CREATE TABLE IF NOT EXISTS audit_log (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  bill_id         INT,
  user            VARCHAR(60) NOT NULL,
  action          VARCHAR(40) NOT NULL,
  field_name      VARCHAR(60),
  old_value       VARCHAR(255),
  new_value       VARCHAR(255),
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE SET NULL,
  INDEX idx_audit_created (created_at)
) ENGINE=InnoDB;

-- 7. Verified Monthly Energy View (Approved Faculty Formulas)
DROP VIEW IF EXISTS v_monthly_energy;
CREATE VIEW v_monthly_energy AS
SELECT
  b.connection_id,
  b.bill_month,
  b.bill_month_label,
  b.period_start,
  b.period_end,
  -- Line a: Solar Generation = (solar_pres - solar_prev) * solar_constant
  (b.solar_present  - b.solar_prev)  * b.solar_constant AS solar_generated_kwh,
  -- Line b: Grid Import = (import_pres - import_prev) * meter_constant
  (b.import_present - b.import_prev) * b.meter_constant AS imported_kwh,
  -- Line c: Grid Export = (export_pres - export_prev) * meter_constant
  (b.export_present - b.export_prev) * b.meter_constant AS exported_kwh,
  -- Line d: Net Energy = b - c
  ((b.import_present - b.import_prev) * b.meter_constant)
    - ((b.export_present - b.export_prev) * b.meter_constant) AS net_energy_kwh,
  -- Total Consumed = a + d
  ((b.solar_present  - b.solar_prev)  * b.solar_constant)
    + ((b.import_present - b.import_prev) * b.meter_constant)
    - ((b.export_present - b.export_prev) * b.meter_constant) AS total_consumed_kwh,
  -- Monthly Savings = a * rate
  ((b.solar_present  - b.solar_prev)  * b.solar_constant) * r.rate_per_unit AS savings_rs,
  r.rate_per_unit,
  b.verified_by,
  b.verified_at
FROM bills b
LEFT JOIN monthly_rates r
  ON r.connection_id = b.connection_id AND r.bill_month = b.bill_month
WHERE b.is_current = 1 AND b.status = 'verified';
