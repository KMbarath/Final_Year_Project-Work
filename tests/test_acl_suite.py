from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from folio.api import create_app
from folio.config import Settings


PASSWORD = "AclTest12345"


def make_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            smtp_host="",
            smtp_from="",
            classifier_path=Path("artifacts/baseline/model.joblib"),
        )
    )


def signup(client, email):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text


def upload(client, filename="document-a.txt"):
    response = client.post(
        "/api/documents",
        files={"file": (filename, b"Passport\nName: Alice\nPassport number: A123", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_ACL_001_user_a_uploads_document_a(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        assert document["filename"] == "document-a.txt"
        assert document["owner_id"] is not None


def test_ACL_002_user_a_can_view_document_a(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        response = user_a.get(f"/api/documents/{document['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == document["id"]


def test_ACL_003_user_b_cannot_view_document_a(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a, TestClient(app) as user_b:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        signup(user_b, "bob@example.com")
        response = user_b.get(f"/api/documents/{document['id']}")
        assert response.status_code == 404


def test_ACL_004_user_b_cannot_download_document_a(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a, TestClient(app) as user_b:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        signup(user_b, "bob@example.com")
        response = user_b.get(f"/api/documents/{document['id']}/download")
        assert response.status_code == 404


def test_ACL_005_user_a_shares_document_a_with_user_b(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        user_a.post("/api/auth/logout")
        signup(user_a, "bob@example.com")
        user_a.post("/api/auth/logout")
        user_a.post("/api/auth/login", json={"email":"alice@example.com","password":PASSWORD})
        response = user_a.post(
            f"/api/documents/{document['id']}/share",
            json={"email": "bob@example.com"},
        )
        assert response.status_code in (200, 201, 204)


def test_ACL_006_user_b_accesses_shared_document(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a, TestClient(app) as user_b:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        signup(user_b, "bob@example.com")
        user_a.post(f"/api/documents/{document['id']}/share", json={"email":"bob@example.com"})
        response = user_b.get(f"/api/documents/{document['id']}")
        assert response.status_code == 200


def test_ACL_007_user_a_revokes_access(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a, TestClient(app) as user_b:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        signup(user_b, "bob@example.com")
        user_a.post(f"/api/documents/{document['id']}/share", json={"email":"bob@example.com"})
        bob_id = user_b.get("/api/auth/me").json()["user"]["id"]
        response = user_a.delete(
            f"/api/documents/{document['id']}/share/{bob_id}"
        )
        assert response.status_code in (200, 204)


def test_ACL_008_user_b_is_denied_after_revoke_scenario(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as user_a, TestClient(app) as user_b:
        signup(user_a, "alice@example.com")
        document = upload(user_a)
        signup(user_b, "bob@example.com")
        user_a.post(f"/api/documents/{document['id']}/share", json={"email":"bob@example.com"})
        bob_id = user_b.get("/api/auth/me").json()["user"]["id"]
        user_a.delete(f"/api/documents/{document['id']}/share/{bob_id}")
        response = user_b.get(f"/api/documents/{document['id']}")
        assert response.status_code == 404
