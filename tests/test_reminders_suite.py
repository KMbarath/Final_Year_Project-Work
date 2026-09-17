from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from folio.api import create_app
from folio.config import Settings


PASSWORD = "ReminderTest12345"


def make_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            smtp_host="",
            smtp_from="",
            classifier_path=Path("artifacts/baseline/model.joblib"),
        )
    )


def signup(client, email="reminders@example.com"):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def upload(client, text, filename):
    response = client.post(
        "/api/documents",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def db_rows(app, query, parameters=()):
    with app.state.assistant.store.connect() as db:
        return db.execute(query, parameters).fetchall()


def test_REM_001_future_expiry_date(tmp_path):
    app = make_app(tmp_path)
    future = date.today() + timedelta(days=90)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nExpiry date: {future.isoformat()}", "future.txt")
        assert document["expiry_date"] == future.isoformat()
        assert client.get("/api/reminders").json() == []
        assert db_rows(app, "SELECT * FROM notifications") == []


def test_REM_002_expiry_within_reminder_window(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=15)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nExpiry date: {due.isoformat()}", "upcoming.txt")
        reminders = client.get("/api/reminders").json()
        assert len(reminders) == 1
        assert reminders[0]["document_id"] == document["id"]
        rows = db_rows(app, "SELECT document_id, expiry_date FROM notifications")
        assert [(row["document_id"], row["expiry_date"]) for row in rows] == [(document["id"], due.isoformat())]


def test_REM_003_expired_document(tmp_path):
    app = make_app(tmp_path)
    expired = date.today() - timedelta(days=3)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nExpiry date: {expired.isoformat()}", "expired.txt")
        reminders = client.get("/api/reminders").json()
        assert reminders[0]["document_id"] == document["id"]
        assert "expired 3 days ago" in reminders[0]["message"]


def test_REM_004_document_without_expiry_date(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, "Passport\nName: Jane Doe\nPassport number: P1234567", "no-expiry.txt")
        assert document["expiry_date"] is None
        assert client.get("/api/reminders").json() == []
        assert db_rows(app, "SELECT * FROM notifications") == []


def test_REM_005_invalid_expiry_date(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, "Passport\nExpiry date: 31/02/2030", "invalid-date.txt")
        assert document["expiry_date"] is None
        assert client.get("/api/reminders").json() == []
        assert db_rows(app, "SELECT * FROM notifications") == []


def test_REM_006_passport_expiry(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nPassport number: P1234567\nExpiry date: {due.isoformat()}", "passport.txt")
        assert document["expiry_date"] == due.isoformat()
        assert len(client.get("/api/reminders").json()) == 1


def test_REM_007_insurance_expiry(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Insurance policy\nPolicy number: INS123\nPolicy end date: {due.isoformat()}", "insurance.txt")
        assert document["expiry_date"] == due.isoformat()
        assert len(client.get("/api/reminders").json()) == 1


def test_REM_008_driving_licence_expiry(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Driving licence\nValid till: {due.isoformat()}", "licence.txt")
        assert document["expiry_date"] == due.isoformat()
        assert len(client.get("/api/reminders").json()) == 1


def test_REM_009_property_tax_due_date_is_not_supported(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Property tax notice\nDue date: {due.isoformat()}", "property-tax.txt")
        assert document["expiry_date"] == due.isoformat(), "Property tax due dates should create reminder dates."
        assert len(client.get("/api/reminders").json()) == 1


def test_REM_010_duplicate_reminder_prevention(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nExpiry date: {due.isoformat()}", "duplicate.txt")
        app.state.notifications.queue()
        app.state.notifications.queue()
        assert len(db_rows(app, "SELECT * FROM notifications WHERE document_id=?", (document["id"],))) == 1
        assert len(db_rows(app, "SELECT * FROM email_outbox WHERE document_id=?", (document["id"],))) == 1


def test_REM_011_notification_delivery(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    sent = []
    monkeypatch.setattr(type(app.state.mailer), "configured", property(lambda self: True))
    monkeypatch.setattr(app.state.mailer, "send", lambda *args: sent.append(args))
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        user = signup(client, "delivery@example.com")
        verification_token = app.state.accounts.verification(user["id"])
        assert app.state.accounts.verify(verification_token)
        sent.clear()
        document = upload(client, f"Insurance\nExpiry date: {due.isoformat()}", "delivery.txt")
        app.state.notifications.tick()
        assert len(sent) == 1
        assert sent[0][0] == "delivery@example.com"
        rows = db_rows(app, "SELECT status, sent_at FROM email_outbox WHERE document_id=?", (document["id"],))
        assert rows[0]["status"] == "sent"
        assert rows[0]["sent_at"] is not None


def test_REM_012_reminder_after_document_deletion(tmp_path):
    app = make_app(tmp_path)
    due = date.today() + timedelta(days=10)
    with TestClient(app) as client:
        signup(client)
        document = upload(client, f"Passport\nExpiry date: {due.isoformat()}", "deleted.txt")
        app.state.notifications.queue()
        assert db_rows(app, "SELECT * FROM notifications WHERE document_id=?", (document["id"],))
        assert db_rows(app, "SELECT * FROM email_outbox WHERE document_id=?", (document["id"],))
        response = client.delete(f"/api/documents/{document['id']}")
        assert response.status_code == 204
        assert db_rows(app, "SELECT * FROM notifications WHERE document_id=?", (document["id"],)) == []
        assert db_rows(app, "SELECT * FROM email_outbox WHERE document_id=?", (document["id"],)) == []
        assert client.get("/api/reminders").json() == []