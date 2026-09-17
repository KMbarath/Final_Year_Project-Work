from datetime import date,timedelta
from pathlib import Path
import json
import re
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from folio.api import create_app
from folio.config import Settings
from folio.storage import Store
from folio.metadata import EntityExtractor
from folio.mail import Mailer

PASSWORD="AccountTest12345"


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, smtp_host="", smtp_from="", classifier_path=Path("artifacts/baseline/model.joblib")))


def signup(client,email):
    response=client.post("/api/auth/signup",json={"email":email,"password":PASSWORD})
    assert response.status_code==201,response.text
    return response.json()["user"]


def upload(client,text,name="passport.txt"):
    response=client.post("/api/documents",files={"file":(name,text.encode(),"text/plain")})
    assert response.status_code==201,response.text
    return response.json()


def verify_user(app,user):
    token=app.state.accounts.verification(user["id"])
    assert app.state.accounts.verify(token)


def test_auth_required_and_password_storage(app):
    with TestClient(app) as c:
        for path in ["/api/documents","/api/reminders","/api/conversations","/api/training"]:
            assert c.get(path).status_code==401
        user=signup(c,"Owner@Example.com")
        assert user["email"]=="owner@example.com"
        assert "HttpOnly" in c.post("/api/auth/login",json={"email":user["email"],"password":PASSWORD}).headers["set-cookie"]
        with app.state.assistant.store.connect() as db:
            saved=db.execute("SELECT password FROM users").fetchone()[0]
        assert PASSWORD not in saved and ":" in saved
        old_cookie=c.cookies.get("folio_session")
        assert c.post("/api/auth/logout").status_code==200
        assert c.get("/api/documents").status_code==401
        assert app.state.accounts.authenticate(old_cookie) is None
        assert c.post("/api/auth/login",json={"email":user["email"],"password":"incorrect"}).status_code==401
        assert c.post("/api/auth/login",json={"email":user["email"],"password":PASSWORD}).status_code==200


def test_dashboard_activity_and_expiry_recommendation(app):
    with TestClient(app) as c:
        signup(c,"dashboard@example.com")
        document=upload(c,f"Passport\nExpiry date: {(date.today()+timedelta(days=15)).isoformat()}","renewal.txt")
        dashboard=c.get("/api/dashboard").json()
        assert dashboard["document_count"]==1 and dashboard["storage_bytes"]>0
        assert dashboard["upcoming_expiries"]==1
        assert dashboard["recommendations"][0]["document_id"]==document["id"]
        events=c.get("/api/activity").json()
        assert any(event["event"]=="document_uploaded" for event in events)


def test_accounts_cannot_access_each_others_documents_chats_or_sources(app):
    with TestClient(app) as a,TestClient(app) as b:
        signup(a,"alice@example.com");signup(b,"bob@example.com")
        document=upload(a,"Passport\nName: Alice\nExpiry date: 2030-05-06\nPassport number: P1234567")
        answer=a.post("/api/chat",json={"question":"give a brief note about this document","document_id":document["id"]}).json()
        assert len(a.get("/api/conversations").json())==1
        assert b.get("/api/documents").json()==[]
        for suffix in ["","/download"]:
            assert b.get("/api/documents/"+document["id"]+suffix).status_code==404
        assert b.delete("/api/documents/"+document["id"]).status_code==404
        assert b.patch("/api/documents/"+document["id"]+"/expiry",json={"expiry_date":"2030-01-01"}).status_code==404
        assert b.get("/api/conversations/"+answer["conversation_id"]).status_code==404
        assert b.post("/api/chat",json={"question":"hi","conversation_id":answer["conversation_id"]}).status_code==404
        assert b.post("/api/conversations",json={"document_id":document["id"]}).status_code==400
        own=upload(b,"Passport\nName: Alice\nExpiry date: 2030-05-06\nPassport number: P1234567")
        assert own["id"]!=document["id"]
        assert len(b.get("/api/documents").json())==1


def test_automatic_expiry_today_overdue_and_correction(app):
    with TestClient(app) as c:
        signup(c,"dates@example.com")
        for days in [0,-3,7]:
            expiry=(date.today()+timedelta(days=days)).isoformat()
            d=upload(c,f"Insurance policy\nPolicy number: P{days}\nThis policy expires on {expiry}.",f"policy-{days}.txt")
            assert d["expiry_date"]==expiry
            assert not d["expiry_confirmed"]
        reminders=c.get("/api/reminders").json()
        assert len(reminders)==3
        assert any("expires today" in r["message"] for r in reminders)
        assert any("expired 3 days ago" in r["message"] for r in reminders)
        d=reminders[0]
        c.patch("/api/documents/"+d["document_id"]+"/expiry",json={"expiry_date":None})
        assert len(c.get("/api/reminders").json())==2
        with app.state.assistant.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM email_outbox WHERE document_id=?",(d["document_id"],)).fetchone()[0]==0


def test_expiry_conflicts_invalid_dates_and_metadata(app):
    with TestClient(app) as c:
        signup(c,"metadata@example.com")
        d=upload(c,"Passport\nName: Sam Kumar\nDate of birth: 12/03/1995\nPassport number: P1234567\nValid until 10 June 2032\nIssue date: 2022-06-10")
        assert d["classification"]["label"]=="passport"
        fields={e["label"]:e["normalized"] for e in d["entities"]}
        assert fields["name"]=="Sam Kumar"
        assert fields["date_of_birth"]=="1995-03-12"
        assert fields["document_number"]=="P1234567"
        assert fields["issue_date"]=="2022-06-10"
        assert d["expiry_date"]=="2032-06-10"
        conflict=upload(c,"Insurance\nExpiry date: 2027-01-01\nExpiry date: 2028-01-01","conflict.txt")
        assert conflict["expiry_date"] is None
        invalid=upload(c,"Passport\nExpiry date: 31/02/2030","invalid.txt")
        assert invalid["expiry_date"] is None


def test_chat_resume_new_chat_and_persistence(app):
    with TestClient(app) as c:
        user=signup(c,"chat@example.com")
        d=upload(c,"Passport\nPassport number: P1234567\nExpiry date: 2032-06-10")
        first=c.post("/api/chat",json={"question":"give a brief note about this document","document_id":d["id"]}).json()
        cid=first["conversation_id"]
        second=c.post("/api/chat",json={"question":"When does it expire?","conversation_id":cid}).json()
        assert second["conversation_id"]==cid
        assert "2032-06-10" in second["answer"]
        history=c.get("/api/conversations/"+cid).json()
        assert len(history["messages"])==4 and history["document_id"]==d["id"]
        reopened=Store(app.state.assistant.store.path.parent)
        assert len(reopened.chat(cid,user["id"])["messages"])==4
        new=c.post("/api/conversations",json={}).json()
        assert new["id"]!=cid and new["messages"]==[]
        assert c.delete("/api/conversations/"+cid).status_code==204
        assert c.get("/api/conversations/"+cid).status_code==404


def test_email_verification_and_due_email_deduplication(app,monkeypatch):
    sent=[]
    monkeypatch.setattr(type(app.state.mailer),"configured",property(lambda s:True))
    monkeypatch.setattr(app.state.mailer,"send",lambda *args:sent.append(args))
    with TestClient(app) as c:
        user=signup(c,"notify@example.com")
        assert len(sent)==1 and sent[0][0]==user["email"]
        token=re.search(r"token=([A-Za-z0-9_-]+)",sent[0][2]).group(1)
        assert "token" not in c.get("/api/auth/me").text
        due=date.today()+timedelta(days=2)
        d=upload(c,f"Insurance policy\nExpiry date: {due.isoformat()}")
        app.state.notifications.tick()
        assert len(sent)==1 # Unverified address receives no document notification.
        assert c.get("/api/auth/verify",params={"token":token},follow_redirects=False).status_code==303
        assert c.get("/api/auth/verify",params={"token":token}).status_code==400
        app.state.notifications.tick()
        app.state.notifications.tick()
        assert len(sent)==2 # One pre-expiry email.
        app.state.notifications.tick(today=due)
        app.state.notifications.tick(today=due+timedelta(days=1))
        assert len(sent)==3 # One expiry email, no repeat every minute.
        assert sent[-1][0]==user["email"] and "reached its expiry" in sent[-1][2]
        c.patch("/api/documents/"+d["id"]+"/expiry",json={"expiry_date":due.isoformat()})
        app.state.notifications.tick(today=due)
        assert len(sent)==3 # Confirming an unchanged date does not resend.


def test_failed_email_retry_and_unconfigured_status(app,monkeypatch):
    with TestClient(app) as c:
        user=signup(c,"retry@example.com");verify_user(app,user)
        upload(c,f"Passport\nExpiry date: {date.today().isoformat()}")
        app.state.notifications.tick()
        assert c.get("/api/status").json()["email_configured"] is False
        monkeypatch.setattr(type(app.state.mailer),"configured",property(lambda s:True))
        send=Mock(side_effect=OSError("test transport failure"))
        monkeypatch.setattr(app.state.mailer,"send",send)
        app.state.notifications.tick()
        with app.state.assistant.store.connect() as db:
            row=db.execute("SELECT * FROM email_outbox").fetchone()
            assert row["status"]=="failed" and row["attempts"]==1
            db.execute("UPDATE email_outbox SET next_attempt=0")
        send.side_effect=None
        app.state.notifications.tick()
        app.state.notifications.tick()
        assert send.call_count==2


def test_smtp_transport_uses_tls_and_account_recipient(tmp_path,monkeypatch):
    smtp=Mock()
    smtp.__enter__=Mock(return_value=smtp);smtp.__exit__=Mock(return_value=False)
    factory=Mock(return_value=smtp)
    monkeypatch.setattr("folio.mail.smtplib.SMTP",factory)
    mailer=Mailer(Settings(data_dir=tmp_path,smtp_host="smtp.example.com",smtp_from="folio@example.com",
                          smtp_username="user",smtp_password="test-secret",smtp_security="starttls"))
    mailer.send("owner@example.com","Expiry","Your document expires today.")
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("user","test-secret")
    message=smtp.send_message.call_args.args[0]
    assert message["To"]=="owner@example.com"
    assert message["Subject"]=="Expiry"
