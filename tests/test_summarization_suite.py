from pathlib import Path

from fastapi.testclient import TestClient

from folio.api import create_app
from folio.config import Settings


PASSWORD = "SummaryTest12345"


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


def upload(client, text, filename):
    response = client.post(
        "/api/documents",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def summarize(client, document_id):
    response = client.post(
        "/api/chat",
        json={"question": "summary", "document_id": document_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_SUM_001_passport_summary(tmp_path):
    source = "Passport\nName: Jane Doe\nPassport number: P1234567\nExpiry date: 2035-06-01"
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "passport-summary@example.com")
        document = upload(client, source, "passport.txt")
        result = summarize(client, document["id"])
        assert result["mode"] == "extractive_overview"
        assert "passport.txt" in result["answer"]
        assert "Passport" in result["answer"]
        assert "Jane Doe" in result["answer"]
        assert "P1234567" in result["answer"]
        assert "2035-06-01" in result["answer"]
        assert len(result["answer"]) < len(source) * 3


def test_SUM_002_medical_report_summary(tmp_path):
    source = "Medical Report\nPatient name: Jane Doe\nDiagnosis: Routine blood test\nHospital: Safe Clinic"
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "medical-summary@example.com")
        document = upload(client, source, "medical.txt")
        result = summarize(client, document["id"])
        assert "medical.txt" in result["answer"]
        assert "Medical Report" in result["answer"]
        assert "Jane Doe" in result["answer"]
        assert "Routine blood test" in result["answer"]


def test_SUM_003_property_document_summary(tmp_path):
    source = "Property Sale Deed\nSurvey Number: 42\nPlot: 7\nBuyer: Jane Doe"
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "property-summary@example.com")
        document = upload(client, source, "property.txt")
        result = summarize(client, document["id"])
        assert "Property Sale Deed" in result["answer"]
        assert "Survey Number: 42" in result["answer"]
        assert "Jane Doe" in result["answer"]


def test_SUM_004_degree_certificate_summary(tmp_path):
    source = "Degree Certificate\nThis certifies that Jane Doe\nBachelor of Science\nUniversity of Example\nGraduation Year: 2024"
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "degree-summary@example.com")
        document = upload(client, source, "degree.txt")
        result = summarize(client, document["id"])
        assert "Degree Certificate" in result["answer"]
        assert "Jane Doe" in result["answer"]
        assert "Bachelor of Science" in result["answer"]


def test_SUM_005_long_document_summary_is_shorter(tmp_path):
    paragraphs = [
        "Passport document for Jane Doe. Passport number P1234567. Expiry date 2035-06-01.",
        *[f"Supporting administrative paragraph {number} with routine reference information." for number in range(1, 20)],
    ]
    source = "\n".join(paragraphs)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "long-summary@example.com")
        document = upload(client, source, "long.txt")
        result = summarize(client, document["id"])
        assert len(result["answer"]) < len(source)
        assert "Jane Doe" in result["answer"]
        assert "P1234567" in result["answer"]


def test_SUM_006_empty_document_is_not_summarized(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "empty-summary@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert response.status_code == 400
        chat = client.post("/api/chat", json={"question": "summary"})
        assert chat.status_code == 200
        assert chat.json()["mode"] == "abstained"
        assert "Upload a document first" in chat.json()["answer"]


def test_SUM_007_unreadable_document_is_not_summarized(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "unreadable-summary@example.com")
        upload_response = client.post(
            "/api/documents",
            files={"file": ("unreadable.txt", b"\x00\x00\x00", "text/plain")},
        )
        assert upload_response.status_code == 400
        chat = client.post("/api/chat", json={"question": "summary"})
        assert chat.status_code == 200
        assert chat.json()["mode"] == "abstained"
        assert "Upload a document first" in chat.json()["answer"]


def test_SUM_008_summary_does_not_add_unsupported_information(tmp_path):
    source = "Passport\nName: Jane Doe\nPassport number: P1234567"
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "unsupported-summary@example.com")
        document = upload(client, source, "limited.txt")
        result = summarize(client, document["id"])
        answer = result["answer"]
        assert "Jane Doe" in answer
        assert "P1234567" in answer
        assert "2035-06-01" not in answer
        assert "Paris" not in answer
        assert "diagnosis" not in answer.lower()