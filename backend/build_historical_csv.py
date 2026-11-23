"""Extract all 67 historical months from the faculty report PDF into CSV."""
import csv
from pathlib import Path
import re
import pypdf

pdf_path = Path(r"C:\Users\admin\Downloads\Solar Energy Generation  Monthly Report_September_ 2026.pdf")
if not pdf_path.exists():
    print("Report PDF not found at", pdf_path)
    exit(1)

reader = pypdf.PdfReader(str(pdf_path))
lines = []
for p in reader.pages:
    for l in p.extract_text().splitlines():
        l = l.strip()
        if l:
            lines.append(l)

months_data = []
curr = {}

for l in lines:
    m_match = re.match(r"^([A-Za-z]+)\s+(\d{4}):", l)
    if m_match:
        if curr and "solar" in curr:
            months_data.append(curr)
        curr = {"month": m_match.group(1), "year": m_match.group(2)}
        continue

    if l.startswith("(a)") or "solar generation" in l.lower():
        nums = re.findall(r"[0-9.,]+", l)
        if nums:
            curr["solar"] = nums[-1].replace(",", "")
    elif l.startswith("(b)") or "imported from" in l.lower():
        nums = re.findall(r"[0-9.,]+", l)
        if nums:
            curr["import"] = nums[-1].replace(",", "")
    elif l.startswith("(c)") or "exported to" in l.lower():
        nums = re.findall(r"[0-9.,]+", l)
        if nums:
            curr["export"] = nums[-1].replace(",", "")
    elif l.startswith("(d)") or "net energy import" in l.lower():
        nums = re.findall(r"[0-9.,]+", l)
        if nums:
            curr["net"] = nums[-1].replace(",", "")
    elif "total" in l.lower() and "consumption" in l.lower():
        nums = re.findall(r"[0-9.,]+", l)
        if nums:
            curr["total"] = nums[-1].replace(",", "")
    elif "rate of rs" in l.lower():
        r_match = re.search(r"rate\s+of\s+rs\s+([0-9.]+)", l, re.IGNORECASE)
        if r_match:
            curr["rate"] = r_match.group(1)
        nums = re.findall(r"[0-9.,]+", l)
        if len(nums) >= 2:
            curr["savings"] = nums[-1].replace(",", "")
    elif "savings" not in curr and re.match(r"^(?:Rs\s*)?[0-9.,]+$", l):
        curr["savings"] = l.replace("Rs", "").replace(",", "").strip()

if curr and "solar" in curr:
    months_data.append(curr)

months_map = {
    "March": "03", "April": "04", "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12", "January": "01", "February": "02"
}

csv_rows = []
for m in months_data:
    m_num = months_map.get(m["month"].capitalize(), "01")
    b_date = f"{m['year']}-{m_num}-01"
    csv_rows.append({
        "bill_month": b_date,
        "month_label": f"{m['month'][:3]}-{m['year'][-2:]}",
        "solar_units_printed": m.get("solar", "0"),
        "import_units_printed": m.get("import", "0"),
        "export_units_printed": m.get("export", "0"),
        "net_import_printed": m.get("net", "0"),
        "rate_per_unit": m.get("rate", "8.05"),
        "meter_constant": "2000",
        "solar_constant": "100"
    })

data_dir = Path(__file__).resolve().parents[1] / "data"
data_dir.mkdir(parents=True, exist_ok=True)
csv_path = data_dir / "historical_records_2021_2026.csv"

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
    writer.writeheader()
    writer.writerows(csv_rows)

print(f"Wrote {len(csv_rows)} rows to {csv_path}")
print("First row:", csv_rows[0])
print("Last row:", csv_rows[-1])
