from io import BytesIO
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from folio.api import create_app
from folio.categories import categorize
from folio.config import Settings


def test_keyword_categories_take_priority_over_synthetic_model_labels():
    assert categorize("UNIQUE IDENTIFICATION AUTHORITY OF INDIA\nAadhaar") == "aadhaar"
    assert categorize("Government of India\nYear of Birth: 1998\nMale") == "aadhaar"
    assert categorize("Republic of India\nPassport No: P1234567") == "passport"
    assert categorize("DRIVING LICENCE\nTransport Department") == "driving_licence"
    assert categorize("Income Tax Department\nPAN number: ABCDE1234F") == "pan"
    assert categorize("A handwritten shopping list") == "other"


def test_category_is_persisted_and_available_through_api(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,classifier_path=tmp_path/"missing.joblib"))
    with TestClient(app) as client:
        assert client.post("/api/auth/signup",json={"email":"categories@example.com","password":"CategoryTest123"}).status_code==201
        documents=[
            ("aadhaar.txt",b"UIDAI\nAadhaar number: 1234 5678 9012"),
            ("passport.txt",b"Republic of India Passport\nPassport number: P1234567"),
            ("licence.txt",b"Driving Licence\nTransport Department\nDL number: TN01 20260000001"),
        ]
        for name,content in documents:
            assert client.post("/api/documents",files={"file":(name,content,"text/plain")}).status_code==201
        categories=client.get("/api/categories").json()
        assert categories=={"aadhaar":1,"passport":1,"driving_licence":1}
        passport=client.get("/api/documents",params={"category":"passport"}).json()
        assert len(passport)==1 and passport[0]["vault_category"]=="passport"


@pytest.mark.skipif(shutil.which("tesseract") is None,reason="Tesseract is not installed")
def test_image_upload_uses_tesseract_and_keyword_category(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,classifier_path=tmp_path/"missing.joblib"))
    image=Image.new("RGB",(1400,500),"white")
    ImageDraw.Draw(image).text((40,80),"DRIVING LICENCE\nTransport Department\nDL number: TN01 20260000001",fill="black",font_size=42)
    payload=BytesIO();image.save(payload,format="PNG")
    with TestClient(app) as client:
        client.post("/api/auth/signup",json={"email":"ocr-categories@example.com","password":"CategoryTest123"})
        response=client.post("/api/documents",files={"file":("licence.png",payload.getvalue(),"image/png")})
        assert response.status_code==201,response.text
        document=response.json()
        assert document["pages"][0]["method"]=="tesseract"
        assert "driving" in document["pages"][0]["text"].lower()
        assert document["vault_category"]=="driving_licence"


@pytest.mark.skipif(shutil.which("tesseract") is None,reason="Tesseract is not installed")
def test_pan_card_image_is_filed_and_its_readable_identifier_is_extracted(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,classifier_path=tmp_path/"missing.joblib"))
    image=Image.new("RGB",(1800,700),"white")
    ImageDraw.Draw(image).text((60,80),"INCOME TAX DEPARTMENT\nPermanent Account Number: ABCDE1234F\n12/03/1995",fill="black",font_size=48)
    payload=BytesIO(); image.save(payload,format="PNG")
    with TestClient(app) as client:
        client.post("/api/auth/signup",json={"email":"pan-ocr@example.com","password":"CategoryTest123"})
        response=client.post("/api/documents",files={"file":("pan.png",payload.getvalue(),"image/png")})
        assert response.status_code==201,response.text
        document=response.json()
        assert document["vault_category"]=="pan"
        assert any(entity["label"]=="document_number" and entity["normalized"]=="ABCDE1234F" for entity in document["entities"])
        refreshed=client.post("/api/documents/"+document["id"]+"/reprocess")
        assert refreshed.status_code==200
        assert refreshed.json()["vault_category"]=="pan"
