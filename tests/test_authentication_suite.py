from pathlib import Path

from fastapi.testclient import TestClient

from folio.api import create_app
from folio.config import Settings


def make_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            smtp_host="",
            smtp_from="",
            classifier_path=Path("artifacts/baseline/model.joblib"),
        )
    )


def test_AUTH_001_valid_registration(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={"email": "user1@example.com", "password": "SecurePass123"},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["user"]["email"] == "user1@example.com"
        assert "folio_session" in client.cookies


def test_AUTH_002_duplicate_email_registration(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        first = client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "SecurePass123"},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "AnotherPass123"},
        )
        assert second.status_code == 400, second.text
        assert "already exists" in second.json()["detail"].lower()


def test_AUTH_003_invalid_email(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={"email": "not-an-email", "password": "SecurePass123"},
        )
        assert response.status_code == 400, response.text
        assert "valid email" in response.json()["detail"].lower()


def test_AUTH_004_empty_registration_fields(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={"email": "", "password": ""})
        assert response.status_code == 422, response.text


def test_AUTH_005_weak_password(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={"email": "weak@example.com", "password": "short"},
        )
        assert response.status_code == 400, response.text
        assert "10 to 128" in response.json()["detail"] or "password" in response.json()["detail"].lower()


def test_AUTH_006_valid_login(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={"email": "login@example.com", "password": "SecurePass123"},
        )
        assert signup.status_code == 201, signup.text
        response = client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "SecurePass123"},
        )
        assert response.status_code == 200, response.text
        assert "folio_session" in client.cookies


def test_AUTH_007_wrong_password(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        client.post(
            "/api/auth/signup",
            json={"email": "wrongpass@example.com", "password": "SecurePass123"},
        )
        response = client.post(
            "/api/auth/login",
            json={"email": "wrongpass@example.com", "password": "WrongPass999"},
        )
        assert response.status_code == 401, response.text
        assert "incorrect" in response.json()["detail"].lower()


def test_AUTH_008_non_existent_user_login(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "SecurePass123"},
        )
        assert response.status_code == 401, response.text


def test_AUTH_009_empty_login_fields(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": "", "password": ""})
        assert response.status_code == 422, response.text


def test_AUTH_010_logout(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        client.post(
            "/api/auth/signup",
            json={"email": "logout@example.com", "password": "SecurePass123"},
        )
        response = client.post("/api/auth/logout")
        assert response.status_code == 200, response.text
        protected = client.get("/api/documents")
        assert protected.status_code == 401, protected.text


def test_AUTH_011_access_protected_page_without_login(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/documents")
        assert response.status_code == 401, response.text


def test_AUTH_012_expired_invalid_authentication_token(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        bad_cookie = "not-a-valid-session-token"
        client.cookies.set("folio_session", bad_cookie)
        response = client.get("/api/documents")
        assert response.status_code == 401, response.text
        assert app.state.accounts.authenticate(bad_cookie) is None


def test_AUTH_013_session_persistence(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={"email": "persist@example.com", "password": "SecurePass123"},
        )
        assert signup.status_code == 201, signup.text
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        payload = me.json()
        assert payload["user"]["email"] == "persist@example.com"
        protected = client.get("/api/documents")
        assert protected.status_code == 200, protected.text


def test_AUTH_014_unauthorized_api_request(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/auth/me")
        assert response.status_code == 401, response.text
        assert "Please log in" in response.json()["detail"]
