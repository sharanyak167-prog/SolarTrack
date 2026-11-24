"""Sample extraction result for the Feb-25 bill (read from the screenshot).
Used by EXTRACTION_MODE=mock and by tests. Not a substitute for real extraction."""

FEB_25 = {
    "consumer": {
        "name": "THE PRESIDENT, ST JOSEPHS ENG COLLEGE VOMANJOOR MANGALORE",
        "rr_number": "KULHT15",
        "account_id": "XXXXXXXXXX",
        "tariff": "HT2C2",
        "voltage_class": "11kv",
        "contract_demand_kva": 350,
        "meter_constant": 2000,
        "solar_constant": 100,
    },
    "billing": {
        "bill_month_label": "Feb-25",
        "bill_date": "2025-03-01",
        "due_date": "2025-03-15",
        "disconnection_date": "2025-03-30",
        "present_reading_date": "2025-03-01",
        "previous_reading_date": "2025-02-01",
        "book_no": "B-3",
        "page_no": "12",
    },
    "meters": {
        "grid_import": {"present_reading": 1524.2360, "previous_reading": 1490.0460, "units_printed": 68380.00},
        "solar_export": {"present_reading": 75.1480, "previous_reading": 74.3640, "units_printed": 1568.00},
        "solar_generation": {"present_reading": 14107.17, "previous_reading": 13787.83, "units_printed": 31934.00},
        "net_energy_import_printed": 66812.00,
        "net_energy_export_printed": 0.00,
        "sub_meter_consumption": -930.30,
        "recorded_demand_kva": 253,
        "power_factor": 0.95,
        "kvah_values": [1593.37, 1557.38, 71982.00],
    },
    "extraction_notes": {
        "page_used": 1,
        "document_is_mescom_bill": True,
        "unclear_fields": [],
        "comments": "mock fixture",
    },
}
