from io import BytesIO

import pymupdf
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from docx import Document

from folio.api import create_app
from folio.config import Settings


def make_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            smtp_host="",
            smtp_from="",
            classifier_path=tmp_path / "model.joblib",
        )
    )


def signup(client, email="user@example.com", password="SecurePass123"):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def make_pdf_bytes(text: str = "Passport\nName: Jane Doe\nExpiry date: 2035-06-01"):
    buffer = BytesIO()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def make_image_bytes(fmt: str = "PNG", text: str = "Passport\nExpiry date: 2035-06-01"):
    image = Image.new("RGB", (500, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 40), text, fill="black")
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def make_docx_bytes(text: str = "Passport\nName: Jane Doe\nExpiry date: 2035-06-01"):
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_scanned_pdf_bytes():
    image = Image.new("RGB", (1000, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 150, 900, 1050), fill="white", outline="black")
    draw.text((180, 360), "PASSPORT\nEXP 2035-06-01", fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    img = Image.open(BytesIO(png))
    pdf_buffer = BytesIO()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png, keep_proportion=True)
    doc.save(pdf_buffer)
    doc.close()
    return pdf_buffer.getvalue()


def test_UPLOAD_001_upload_valid_pdf(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "pdf@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("passport.pdf", make_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "passport.pdf"
        assert payload["pages"]


def test_UPLOAD_002_upload_valid_jpg(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "jpg@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("passport.jpg", make_image_bytes("JPEG"), "image/jpeg")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "passport.jpg"


def test_UPLOAD_003_upload_valid_png(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "png@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("passport.png", make_image_bytes("PNG"), "image/png")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "passport.png"


def test_UPLOAD_004_upload_supported_word_document(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "word@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("passport.docx", make_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "passport.docx"


def test_UPLOAD_005_upload_scanned_document(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "scan@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("scanned.pdf", make_scanned_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "scanned.pdf"


def test_UPLOAD_006_upload_empty_file(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "empty@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert response.status_code == 400, response.text
        assert "nonempty" in response.json()["detail"].lower()


def test_UPLOAD_007_upload_corrupted_pdf(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "corrupt@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("broken.pdf", b"%PDF-1.4\nnot-a-real-pdf\n", "application/pdf")},
        )
        assert response.status_code in (400, 500), response.text
        assert "document" in response.json().get("detail", "").lower() or response.status_code == 500


def test_UPLOAD_008_upload_unsupported_file_type(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "unsupported@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("notes.csv", b"id,name\n1,test\n", "text/csv")},
        )
        assert response.status_code == 400, response.text
        assert "supported files" in response.json()["detail"].lower()


def test_UPLOAD_009_upload_oversized_file(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "large@example.com")
        big = b"A" * (20 * 1024 * 1024 + 1)
        response = client.post(
            "/api/documents",
            files={"file": ("large.txt", big, "text/plain")},
        )
        assert response.status_code == 413, response.text
        assert "20 MB" in response.json()["detail"]


def test_UPLOAD_010_upload_duplicate_document(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "dup@example.com")
        payload = make_pdf_bytes("Passport\nName: Jane Doe\nExpiry date: 2035-06-01")
        first = client.post(
            "/api/documents",
            files={"file": ("duplicate.pdf", payload, "application/pdf")},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/documents",
            files={"file": ("duplicate.pdf", payload, "application/pdf")},
        )
        assert second.status_code == 201, second.text
        assert second.json().get("duplicate") is True


def test_UPLOAD_011_upload_multiple_documents(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "multi@example.com")
        responses = [
            client.post(
                "/api/documents",
                files={"file": (name, payload, content_type)},
            )
            for name, payload, content_type in [
                ("doc1.txt", b"Passport\nName: One\nExpiry date: 2030-01-01\n", "text/plain"),
                ("doc2.txt", b"Insurance\nPolicy number: INS-123\n", "text/plain"),
                ("doc3.txt", b"Medical\nPatient name: Jane\n", "text/plain"),
            ]
        ]
        assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
        assert len(client.get("/api/documents").json()) == 3


def test_UPLOAD_012_unauthorized_upload(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("private.pdf", make_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 401, response.text
        assert "Please log in" in response.json()["detail"]


def test_UPLOAD_013_upload_with_missing_metadata(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "meta@example.com")
        response = client.post(
            "/api/documents",
            files={"file": ("missing-metadata.pdf", make_pdf_bytes("A document with no labelled metadata."), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["filename"] == "missing-metadata.pdf"
        assert payload["entities"] == []


def test_UPLOAD_014_delete_uploaded_document(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        signup(client, "delete@example.com")
        upload = client.post(
            "/api/documents",
            files={"file": ("to-delete.pdf", make_pdf_bytes(), "application/pdf")},
        )
        doc_id = upload.json()["id"]
        delete_response = client.delete(f"/api/documents/{doc_id}")
        assert delete_response.status_code == 204, delete_response.text
        fetch_response = client.get(f"/api/documents/{doc_id}")
        assert fetch_response.status_code == 404, fetch_response.text
