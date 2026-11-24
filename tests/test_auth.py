"""Tests for authentication, JWT issuance, roles, and user management."""
import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, hash_password, verify_password
from app.main import create_app
from app import db
from app.models import User


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODE", "mock")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-that-is-at-least-32-characters")
    app = create_app(f"sqlite:///{tmp_path / 'test_auth.db'}")
    with db.SessionLocal() as session:
        session.add_all([User(username="admin", hashed_password=hash_password("admin123"), role="admin", is_active=True), User(username="viewer", hashed_password=hash_password("viewer123"), role="viewer", is_active=True)])
        session.commit()
    with TestClient(app) as c:
        yield c


def test_password_hashing():
    pwd = "SecretPassword123"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword", h) is False


def test_login_flow(client):
    # Successful admin login
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["role"] == "admin"
    admin_token = body["access_token"]

    # Verify /auth/me
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert me["username"] == "admin"
    assert me["role"] == "admin"

    # Viewer login
    r_v = client.post("/auth/login", json={"username": "viewer", "password": "viewer123"})
    assert r_v.status_code == 200
    assert r_v.json()["role"] == "viewer"

    # Bad password
    bad = client.post("/auth/login", json={"username": "admin", "password": "badpassword"})
    assert bad.status_code == 401


def test_role_enforcement(client):
    # Login viewer
    v_token = client.post("/auth/login", json={"username": "viewer", "password": "viewer123"}).json()["access_token"]
    # Login admin
    a_token = client.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]

    # Viewer cannot list users (admin only)
    r = client.get("/users", headers={"Authorization": f"Bearer {v_token}"})
    assert r.status_code == 403

    # Admin can list users
    r = client.get("/users", headers={"Authorization": f"Bearer {a_token}"})
    assert r.status_code == 200
    users = r.json()
    assert any(u["username"] == "admin" for u in users)

    # Viewer can access read-only stats
    r_stats = client.get("/stats/monthly?connection_id=1", headers={"Authorization": f"Bearer {v_token}"})
    assert r_stats.status_code == 200


def test_user_management(client):
    a_token = client.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    # Create new user
    new_user = client.post("/users", json={"username": "operator1", "password": "op1password123", "role": "admin", "full_name": "Operator One"}, headers=headers)
    assert new_user.status_code == 201
    uid = new_user.json()["id"]

    # Update user role to viewer
    up = client.patch(f"/users/{uid}", json={"role": "viewer"}, headers=headers)
    assert up.status_code == 200
    assert up.json()["role"] == "viewer"

    # Deactivate user
    deact = client.patch(f"/users/{uid}", json={"is_active": False}, headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    # Deactivated user cannot log in
    log = client.post("/auth/login", json={"username": "operator1", "password": "op1password123"})
    assert log.status_code == 401


def test_header_cannot_bypass_login(client):
    assert client.get("/users", headers={"X-User": "admin"}).status_code == 401
    assert client.get("/users?token=bogus").status_code == 401
