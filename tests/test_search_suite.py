from pathlib import Path

from fastapi.testclient import TestClient

from folio.api import create_app
from folio.config import Settings
from folio.retrieval import Retriever


def make_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            smtp_host="",
            smtp_from="",
            classifier_path=Path("artifacts/baseline/model.joblib"),
        )
    )


def document(document_id, filename, text, classification="unknown"):
    return {
        "id": document_id,
        "filename": filename,
        "classification": {"label": classification},
        "entities": [],
        "pages": [{"page": 1, "text": text}],
    }


def search(question, documents):
    return Retriever().search(question, documents)


def filenames(results):
    return [result["filename"] for result in results]


def test_SEARCH_001_keyword_search():
    results = search("passport", [document("1", "passport.txt", "Passport number P1234567")])
    assert results
    assert "passport.txt" in filenames(results)


def test_SEARCH_002_category_search():
    results = search(
        "insurance policy",
        [document("1", "policy.txt", "Health insurance policy Policy number INS12345", "insurance")],
    )
    assert results
    assert results[0]["filename"] == "policy.txt"


def test_SEARCH_003_date_search():
    results = search("2035-06-01", [document("1", "passport.txt", "Expiry date 2035-06-01")])
    assert results
    assert "2035-06-01" in results[0]["text"]


def test_SEARCH_004_ocr_content_search():
    results = search(
        "OCR extracted passport number",
        [document("1", "scan.png", "OCR extracted text Passport number P1234567")],
    )
    assert results
    assert results[0]["filename"] == "scan.png"


def test_SEARCH_005_partial_keyword_search():
    results = search("passpor", [document("1", "passport.txt", "Passport number P1234567")])
    assert results, "Partial keyword should match the document content."


def test_SEARCH_006_case_insensitive_search():
    results = search("PASSPORT", [document("1", "passport.txt", "Passport number P1234567")])
    assert results
    assert results[0]["filename"] == "passport.txt"


def test_SEARCH_007_no_result_search():
    results = search("unrelated astronomy term", [document("1", "passport.txt", "Passport number P1234567")])
    assert results == []


def test_SEARCH_008_search_across_multiple_documents():
    results = search(
        "Project Atlas",
        [
            document("1", "passport.txt", "Passport number P1234567"),
            document("2", "insurance.txt", "Insurance policy includes Project Atlas coverage"),
        ],
    )
    assert results
    assert results[0]["document_id"] == "2"


def test_SEARCH_009_unauthorized_document_search(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/documents")
        assert response.status_code == 401


def test_SEARCH_010_search_special_characters():
    results = search(
        "P-123/45",
        [document("1", "passport.txt", "Passport number P-123/45")],
    )
    assert results
    assert "P-123/45" in results[0]["text"]