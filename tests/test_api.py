"""End to end: upload -> review -> edit -> verify -> rate -> stats, using mock extraction."""
from copy import deepcopy
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from app.extraction import extractor
from app.extraction.fixtures import FEB_25
from app.main import create_app
from app.auth import get_current_user
from app.models import User
from fastapi import Request


def march_extraction():
    """Synthetic March bill: numbers from sir's handwritten note, other fields copied from Feb."""
    x = deepcopy(FEB_25)
    x["billing"].update(bill_month_label="Mar-25", bill_date="2025-04-01", present_reading_date="2025-04-01",
                        previous_reading_date="2025-03-01")
    x["meters"].update(
        grid_import={"present_reading": 1562.8340, "previous_reading": 1524.2360, "units_printed": 77196},
        solar_export={"present_reading": 76.4530, "previous_reading": 75.1480, "units_printed": 2610},
        solar_generation={"present_reading": 14478.19, "previous_reading": 14107.17, "units_printed": 37102},
        net_energy_import_printed=74586)
    return x


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODE", "mock")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-that-is-at-least-32-characters")
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    def test_user(request: Request):
        return User(username=request.headers.get("X-User", "admin"), role="admin", is_active=True)
    app.dependency_overrides[get_current_user] = test_user
    with TestClient(app) as c:
        yield c


def upload(client, content=b"%PDF-1.4 a", name="feb.pdf", **params):
    return client.post("/bills/upload", files={"file": (name, content, "application/pdf")}, params=params)


def test_full_flow(client, monkeypatch):
    r = upload(client)
    assert r.status_code == 201, r.text
    feb = r.json()
    assert feb["status"] == "extracted" and feb["validation_flags"] == []
    assert D(feb["energy"]["total_consumed"]) == D(98746)
    assert feb["energy"]["savings"] is None             # no rate yet

    assert client.post(f"/bills/{feb['id']}/verify", headers={"X-User": "staff1"}).json()["verified_by"] == "staff1"

    monkeypatch.setattr(extractor, "extract_bill", lambda path: march_extraction())
    mar = upload(client, b"%PDF-1.4 b", "mar.pdf").json()
    assert mar["validation_flags"] == []                # chains cleanly onto Feb
    assert client.post(f"/bills/{mar['id']}/verify").status_code == 200

    conn_id = mar["connection_id"]
    assert client.put("/rates", json={"connection_id": conn_id, "bill_month": "2025-03-15", "rate_per_unit": "7"}).status_code == 200

    rows = client.get("/stats/monthly", params={"connection_id": conn_id}).json()
    assert [r["bill_month"] for r in rows] == ["2025-02-01", "2025-03-01"]
    e = rows[1]["energy"]
    assert (D(e["solar_generated"]), D(e["imported"]), D(e["exported"]), D(e["net_energy"]),
            D(e["total_consumed"]), D(e["savings"])) == (D(37102), D(77196), D(2610), D(74586), D(111688), D(259714))

    summ = client.get("/stats/summary", params={"connection_id": conn_id, "start": "2025-02-01", "end": "2025-03-31"}).json()
    assert summ["months_included"] == 2 and summ["missing_rates"] == ["2025-02-01"]
    assert D(summ["total"]["total_consumed"]) == D(98746 + 111688)
    assert summ["total"]["savings"] is None             # Feb has no rate yet

    client.put("/rates", json={"connection_id": conn_id, "bill_month": "2025-02-01", "rate_per_unit": "6.5"})
    summ = client.get("/stats/summary", params={"connection_id": conn_id, "start": "2025-02-01", "end": "2025-03-01"}).json()
    assert summ["missing_rates"] == [] and D(summ["total"]["savings"]) == D("31934") * D("6.5") + D(259714)


def test_duplicate_file_rejected(client):
    first = upload(client).json()
    r = upload(client)
    assert r.status_code == 409 and r.json()["detail"]["existing_bill_id"] == first["id"]


def test_edit_fixes_error_and_is_audited_and_unverifies(client):
    bill = upload(client).json()
    bad = client.patch(f"/bills/{bill['id']}", json={"import_present": "1524.2960"}).json()
    assert bad["status"] == "needs_review"
    assert any(f["code"] == "E_UNITS_MISMATCH" for f in bad["validation_flags"])
    assert client.post(f"/bills/{bill['id']}/verify").status_code == 409     # errors block verification

    fixed = client.patch(f"/bills/{bill['id']}", json={"import_present": "1524.2360"}).json()
    assert fixed["validation_flags"] == []
    assert client.post(f"/bills/{bill['id']}/verify").json()["status"] == "verified"

    again = client.patch(f"/bills/{bill['id']}", json={"solar_prev": "13787.80"}).json()
    assert again["status"] == "needs_review" and again["verified_by"] is None   # editing un-verifies


def test_second_upload_for_verified_month_needs_replace(client):
    bill = upload(client).json()
    client.post(f"/bills/{bill['id']}/verify")
    assert upload(client, b"%PDF-1.4 other").status_code == 409
    r = upload(client, b"%PDF-1.4 other", replace="true")
    assert r.status_code == 201 and r.json()["version"] == 2
    assert client.get(f"/bills/{bill['id']}").json()["is_current"] is False


def test_unverified_bills_do_not_count_in_stats(client):
    bill = upload(client).json()
    assert client.get("/stats/monthly", params={"connection_id": bill["connection_id"]}).json() == []


def test_bad_uploads(client):
    assert upload(client, b"x", "notes.txt").status_code == 415
    assert upload(client, b"", "empty.pdf").status_code == 400


def test_original_file_can_be_fetched(client):
    bill = upload(client, b"%PDF-1.4 hello").json()
    r = client.get(f"/bills/{bill['id']}/file")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 hello"


def test_negative_rate_rejected(client):
    bill = upload(client).json()
    r = client.put("/rates", json={"connection_id": bill["connection_id"], "bill_month": "2025-02-01", "rate_per_unit": "-1"})
    assert r.status_code == 422


def test_end_to_end_report_pdf(client):
    bill = upload(client).json()
    assert client.patch(f"/bills/{bill['id']}", json={"solar_present": bill["solar_present"]}).status_code == 200
    assert client.post(f"/bills/{bill['id']}/verify").status_code == 200
    assert client.put('/rates', json={'connection_id': bill['connection_id'], 'bill_month': '2025-02-01', 'rate_per_unit': '7'}).status_code == 200
    report = client.get('/reports/download', params={'connection_id': bill['connection_id'], 'start': '2025-02-01', 'end': '2025-03-01', 'include_ai': False})
    assert report.status_code == 200 and report.content.startswith(b'%PDF-')
    import io, pypdf
    text = ''.join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(report.content)).pages)
    assert '31,934' in text
    assert 'Missing verified months' in text
