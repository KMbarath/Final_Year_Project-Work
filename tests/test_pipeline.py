from datetime import date,timedelta
from pathlib import Path
import io
import pymupdf
import pytest
from fastapi.testclient import TestClient
from folio.api import create_app
from folio.config import Settings
from folio.metadata import EntityExtractor,parse_date
from folio.retrieval import chunk_pages,Retriever
from folio.prompt_extraction import PromptCatalog, PromptExtractor
from folio.config import ROOT
from training.data import generate,load_rows,split_rows,fingerprint

TEXT=b"Republic of India Passport\nName: Sam Kumar\nPassport number: P1234567\nExpiry date: 2032-06-10"


@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,classifier_path=tmp_path/"missing.joblib"))
    with TestClient(app) as client:
        response=client.post("/api/auth/signup",json={"email":"tester@example.com","password":"SecureTestPass123"})
        assert response.status_code==201,response.text
        yield client


def upload(client,text=TEXT,name="passport.txt"):
    r=client.post("/api/documents",files={"file":(name,text,"text/plain")})
    assert r.status_code==201,r.text
    return r.json()


def test_document_lifecycle_sources_and_persistence(client):
    d=upload(client)
    assert d["expiry_date"]=="2032-06-10"
    assert not d["expiry_confirmed"]
    assert d["classification"]["label"]=="unknown"
    assert upload(client)["duplicate"]
    assert len(client.get("/api/documents").json())==1
    result=client.post("/api/chat",json={"question":"When does my passport expire?"}).json()
    assert "2032-06-10" in result["answer"]
    assert result["sources"][0]["document_id"]==d["id"]
    assert result["sources"][0]["page"]==1
    due=(date.today()+timedelta(days=12)).isoformat()
    assert client.get("/api/reminders").json()==[]
    assert client.patch("/api/documents/"+d["id"]+"/expiry",json={"expiry_date":due}).status_code==200
    assert len(client.get("/api/reminders").json())==1
    assert len(client.get("/api/reminders").json())==1
    assert client.delete("/api/documents/"+d["id"]).status_code==204
    assert client.get("/api/reminders").json()==[]
    assert client.get("/api/documents/"+d["id"]).status_code==404
    assert client.post("/api/chat",json={"question":"Passport expiry?"}).json()["mode"]=="abstained"


def test_scope_and_insufficient_evidence(client):
    a=upload(client)
    b=upload(client,b"Health insurance policy\nPolicy number: INS9876","policy.txt")
    r=client.post("/api/chat",json={"question":"policy number","document_id":b["id"]}).json()
    assert all(s["document_id"]==b["id"] for s in r["sources"])
    assert client.post("/api/chat",json={"question":"Who discovered Neptune?"}).json()["mode"]=="abstained"
    assert client.post("/api/chat",json={"question":"expiry","document_id":"missing"}).status_code==400


def test_upload_validation_and_local_origin(client):
    assert client.post("/api/documents",files={"file":("x.exe",b"binary")}).status_code==400
    assert client.post("/api/documents",files={"file":("x.txt",b"")}).status_code==400
    assert client.post("/api/chat",json={"question":" "}).status_code==422
    assert client.post("/api/chat",json={"question":"  "}).status_code==400
    assert client.get("/api/documents",headers={"Origin":"https://untrusted.example"}).status_code==403
    assert client.get("/api/documents",headers={"Host":"untrusted.example"}).status_code==403
    assert client.get("/").status_code==200
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_native_pdf_page_provenance(client):
    doc=pymupdf.open()
    for text in ["Medical report patient hemoglobin normal findings","Passport number: P9876543 expiry date: 2033-01-02"]:
        page=doc.new_page();page.insert_text((50,60),text)
    d=upload(client,doc.tobytes(),"sample.pdf")
    assert len(d["pages"])==2 and all(p["method"]=="native_pdf" for p in d["pages"])
    r=client.post("/api/chat",json={"question":"Passport number"}).json()
    assert r["sources"][0]["page"]==2


def test_reminder_catchup_and_date_correction(client):
    d=upload(client)
    path="/api/documents/"+d["id"]+"/expiry"
    assert client.patch(path,json={"expiry_date":"2025-02-30"}).status_code==422
    client.patch(path,json={"expiry_date":(date.today()-timedelta(days=2)).isoformat()})
    assert "expired" in client.get("/api/reminders").json()[0]["message"]
    client.patch(path,json={"expiry_date":(date.today()+timedelta(days=50)).isoformat()})
    assert client.get("/api/reminders").json()==[]
    client.patch(path,json={"expiry_date":None})
    assert client.get("/api/documents/"+d["id"]).json()["expiry_date"] is None


def test_entity_offsets_and_dates():
    text=TEXT.decode()
    for e in EntityExtractor().extract(text):
        assert text[e["start"]:e["end"]]==e["text"]
    assert parse_date("10 June 2032")=="2032-06-10"
    assert parse_date("31/02/2032") is None


def test_chunking_and_empty_search():
    doc={"id":"1","filename":"long.txt","pages":[{"page":1,"text":" ".join(str(i) for i in range(500))}]}
    chunks=chunk_pages(doc,size=100,overlap=20)
    words={w for c in chunks for w in c["text"].split()}
    assert len(words)==500
    assert Retriever().search("nothing",[])==[]
    with pytest.raises(ValueError):chunk_pages(doc,size=20,overlap=20)


def test_prompt_catalog_and_structured_facts():
    catalog = PromptCatalog(ROOT / "prompts.yaml")
    assert len(catalog.specs) >= 40
    text = "INCOME TAX DEPARTMENT\nName: LOHITH KUMAR A\nPAN No: AOQPL6521H\nDate: 04/11/1986"
    assert catalog.identify(text) == "pan"
    doc_type, entities = PromptExtractor(ROOT / "prompts.yaml").extract(text)
    assert doc_type == "pan"
    assert any(e["label"] == "pan_no" and e["normalized"] == "AOQPL6521H" for e in entities)
    document={"id":"1","filename":"pan.txt","entities":entities,"pages":[{"page":1,"text":text}]}
    hits=Retriever().search("What is the PAN number?",[document])
    assert hits and hits[0]["kind"] == "structured_facts"
    semantic = Retriever("lsa").search("PAN identifier", [document])
    assert semantic and semantic[0]["semantic_score"] is not None


def test_split_groups_and_duplicates(tmp_path):
    path=tmp_path/"data.csv";generate(path,per_template=2)
    rows=load_rows(path);splits=split_rows(rows)
    for a,b in [("train","test"),("train","validation"),("validation","test")]:
        assert not {r["group"] for r in splits[a]} & {r["group"] for r in splits[b]}
        assert not {fingerprint(r["text"]) for r in splits[a]} & {fingerprint(r["text"]) for r in splits[b]}


def test_optional_features_report_unavailable(client):
    assert client.post("/api/speak",json={"text":"hello"}).status_code==503
    upload(client)
    assert client.post("/api/chat",json={"question":"Passport expiry","language":"hi"}).status_code==503


def test_greeting_avoids_model_loading(client, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("Greeting should not load retrieval models")
    monkeypatch.setattr(client.app.state.assistant.retriever, "search", must_not_run)
    result = client.post("/api/chat", json={"question": "hi"}).json()
    assert result["mode"] == "greeting"
    assert result["sources"] == []


def test_brief_note_is_scoped_and_has_sources(client, monkeypatch):
    chosen = upload(client, b"University semester examination record\nCourse: Data Structures\nResult: Passed", "semester.pdf.txt")
    upload(client, b"Insurance policy unrelated private detail", "insurance.txt")
    def must_not_run(*args, **kwargs):
        raise AssertionError("Overview should not depend on semantic retrieval")
    monkeypatch.setattr(client.app.state.assistant.retriever, "search", must_not_run)
    response = client.post("/api/chat", json={"question": "give a brief note about this document", "document_id": chosen["id"]})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "extractive_overview"
    assert "Data Structures" in result["answer"]
    assert "unrelated private detail" not in result["answer"]
    assert all(s["document_id"] == chosen["id"] for s in result["sources"])
    assert result["sources"][0]["page"] == 1
    assert client.post("/api/chat", json={"question": "summarize this document"}).json()["mode"] == "clarification"


def test_overview_without_documents(client):
    result = client.post("/api/chat", json={"question": "give a brief note about this document"}).json()
    assert result["mode"] == "abstained"
    assert result["sources"] == []
