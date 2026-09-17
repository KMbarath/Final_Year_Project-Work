from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from folio.extraction import Extractor, FeatureUnavailable


OCR_TEXT = "PASSPORT\nNAME JANE DOE\nNUMBER P1234567\nEXPIRY 2035-06-01"
FONT_PATH = Path("C:/Windows/Fonts/arial.ttf")
TAMIL_FONT_PATH = Path("C:/Windows/Fonts/Nirmala.ttc")


def font(size=48, tamil=False):
    return ImageFont.truetype(str(TAMIL_FONT_PATH if tamil else FONT_PATH), size)


def text_image(text=OCR_TEXT, size=(1400, 700), font_size=48):
    image = Image.new("RGB", size, "white")
    tamil = any("\u0b80" <= character <= "\u0bff" for character in text)
    ImageDraw.Draw(image).multiline_text((80, 80), text, fill="black", font=font(font_size, tamil=tamil), spacing=24)
    return image


def image_bytes(image, image_format):
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def clear_pdf_bytes(text=OCR_TEXT):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox((72, 72, 540, 700), text, fontsize=24)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def scanned_pdf_bytes(image):
    png = image_bytes(image, "PNG")
    document = pymupdf.open()
    page = document.new_page(width=image.width, height=image.height)
    page.insert_image(page.rect, stream=png)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def extract(filename, content):
    try:
        pages = Extractor("tesseract").extract(content, filename)
    except FeatureUnavailable as exc:
        pytest.skip(str(exc))
    return "\n".join(page["text"] for page in pages), pages


def normalized(text):
    return " ".join(text.upper().split())


def assert_expected(expected, actual):
    actual_normalized = normalized(actual)
    missing = [token for token in normalized(expected).split() if token not in actual_normalized]
    assert not missing, f"Expected text missing: {missing}; actual extracted text: {actual!r}"


def test_OCR_001_clear_pdf():
    actual, pages = extract("clear.pdf", clear_pdf_bytes())
    assert pages[0]["method"] == "native_pdf"
    assert_expected(OCR_TEXT, actual)


def test_OCR_002_scanned_pdf():
    actual, pages = extract("scanned.pdf", scanned_pdf_bytes(text_image()))
    assert pages[0]["method"] == "tesseract"
    assert_expected("PASSPORT NAME JANE DOE NUMBER P1234567 EXPIRY 2035-06-01", actual)


def test_OCR_003_jpg_image():
    actual, pages = extract("document.jpg", image_bytes(text_image(), "JPEG"))
    assert pages[0]["method"] == "tesseract"
    assert_expected(OCR_TEXT, actual)


def test_OCR_004_png_image():
    actual, pages = extract("document.png", image_bytes(text_image(), "PNG"))
    assert pages[0]["method"] == "tesseract"
    assert_expected(OCR_TEXT, actual)


def test_OCR_005_blurry_document():
    image = text_image().filter(ImageFilter.GaussianBlur(radius=1.5))
    actual, _ = extract("blurry.png", image_bytes(image, "PNG"))
    assert_expected("PASSPORT NAME JANE DOE", actual)


def test_OCR_006_rotated_document():
    image = text_image().rotate(90, expand=True, fillcolor="white")
    actual, _ = extract("rotated.png", image_bytes(image, "PNG"))
    assert_expected("PASSPORT NAME JANE DOE", actual)


def test_OCR_007_low_resolution_document():
    image = text_image(size=(420, 210), font_size=18)
    actual, _ = extract("low-resolution.png", image_bytes(image, "PNG"))
    assert_expected("PASSPORT NAME JANE DOE", actual)


def test_OCR_008_document_containing_numbers():
    expected = "DOCUMENT NUMBER 1234567890 POLICY 987654321"
    actual, _ = extract("numbers.png", image_bytes(text_image(expected), "PNG"))
    assert_expected(expected, actual)


def test_OCR_009_document_containing_dates():
    expected = "ISSUED 2024-01-15 EXPIRY 2035-06-01"
    actual, _ = extract("dates.png", image_bytes(text_image(expected), "PNG"))
    assert_expected(expected, actual)


def test_OCR_010_tamil_document():
    expected = "கடவுச்சீட்டு பெயர்"
    actual, _ = extract("tamil.png", image_bytes(text_image(expected), "PNG"))
    assert_expected(expected, actual)


def test_OCR_011_document_with_missing_text():
    image = text_image("PASSPORT\nNAME JANE DOE\n[NO EXPIRY FIELD]")
    actual, _ = extract("missing-text.png", image_bytes(image, "PNG"))
    assert_expected("PASSPORT NAME JANE DOE", actual)
    assert "2035-06-01" not in actual


def test_OCR_012_completely_unreadable_document():
    image = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, 1400, 25):
        draw.line((x, 0, 1400 - x, 700), fill=(210, 210, 210), width=8)
    actual, _ = extract("unreadable.png", image_bytes(image, "PNG"))
    assert len(normalized(actual)) < 20, f"Expected no readable text; actual extracted text: {actual!r}"