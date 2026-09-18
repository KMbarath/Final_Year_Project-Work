"""Native PDF extraction and explicit, selectable OCR adapters."""
import io
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[1]


class FeatureUnavailable(RuntimeError):
    pass


class Extractor:
    def __init__(self, backend="tesseract", max_pages=80):
        self.backend, self.max_pages = backend, max_pages
        self._paddle = None

    def ocr(self, image):
        if image.width * image.height > 30_000_000:
            raise ValueError("Image exceeds 30 megapixels.")
        # Improve the OCR copy only; preserve the original upload unchanged.  ID
        # cards are often low-resolution photographs, where Tesseract benefits
        # from a larger, greyscale, sharpened image.
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.width < 1600:
            scale = 1600 / image.width
            image = image.resize((1600, max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        image = ImageEnhance.Contrast(image).enhance(1.35)
        image = ImageEnhance.Sharpness(image).enhance(1.5)
        if self.backend == "paddle":
            try:
                from paddleocr import PaddleOCR
                import numpy as np
            except ImportError as exc:
                raise FeatureUnavailable("Install the OCR extra to enable PaddleOCR.") from exc
            if self._paddle is None:
                self._paddle = PaddleOCR(lang="en", use_doc_orientation_classify=False,
                                        use_doc_unwarping=False, use_textline_orientation=False)
            results = self._paddle.predict(np.asarray(image))
            lines = []
            for result in results:
                lines.extend(result["rec_texts"])
            return "\n".join(lines)
        executable = shutil.which("tesseract")
        if not executable:
            raise FeatureUnavailable("Install Tesseract or select PaddleOCR with FOLIO_OCR=paddle.")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "page.png"
            image.save(path)
            tessdata = ROOT / "artifacts" / "tessdata"
            orientation = subprocess.run([executable, str(path), "stdout", "--psm", "0", "-l", "osd"],
                                         capture_output=True, timeout=30, check=False)
            orientation_text = orientation.stdout.decode("utf-8", errors="replace")
            match = re.search(r"Rotate:\s*(\d+)", orientation_text)
            confidence = re.search(r"Orientation confidence:\s*([0-9.]+)", orientation_text)
            orientation_confidence = float(confidence.group(1)) if confidence else 0.0
            # OSD is unreliable on short card text.  Only rotate when it has a
            # meaningful confidence score; a low-confidence rotation can turn a
            # readable card into an unreadable one.
            if match and orientation_confidence >= 3.0:
                degrees = int(match.group(1)) % 360
                if degrees:
                    image = image.rotate(-degrees, expand=True, fillcolor="white")
                    image.save(path)
            # Sparse-text mode is more reliable for photographed cards than the
            # default multi-column page layout mode.
            result = subprocess.run([executable, str(path), "stdout", "-l", "eng", "--psm", "11"],
                                    capture_output=True, timeout=90, check=True)
            text = result.stdout.decode("utf-8", errors="replace").strip()
            if (tessdata / "tam.traineddata").exists():
                tamil = subprocess.run([executable, "--tessdata-dir", str(tessdata), str(path), "stdout", "-l", "tam"],
                                              capture_output=True, timeout=90, check=True)
                multilingual_text = tamil.stdout.decode("utf-8", errors="replace").strip()
                ascii_letters = sum(character.isascii() and character.isalpha() for character in text)
                non_ascii_letters = sum((not character.isascii()) and character.isalpha() for character in multilingual_text)
                if non_ascii_letters > ascii_letters:
                    text = multilingual_text
            return text

    def extract(self, content: bytes, filename: str):
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("The file is not a text document.")
            return [{"page": 1, "text": text.strip(), "method": "text"}]
        if suffix == ".docx":
            try:
                import docx
            except ImportError as exc:
                raise FeatureUnavailable("Install python-docx to enable DOCX support.") from exc
            try:
                document = docx.Document(io.BytesIO(content))
            except Exception as exc:
                raise ValueError("Could not read the DOCX document.") from exc
            text = "\n".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
            return [{"page": 1, "text": text.strip(), "method": "docx"}]
        if suffix == ".doc":
            try:
                import mammoth
            except ImportError as exc:
                raise FeatureUnavailable("Install mammoth to enable DOC support.") from exc
            try:
                result = mammoth.extract_raw_text(io.BytesIO(content))
                text = result.value.strip()
            except Exception as exc:
                raise ValueError("Could not read the DOC document.") from exc
            return [{"page": 1, "text": text, "method": "doc"}]
        if suffix == ".pdf":
            pages = []
            try:
                pdf = pymupdf.open(stream=content, filetype="pdf")
            except Exception as exc:
                raise ValueError("Could not read the PDF document.") from exc
            with pdf:
                if pdf.needs_pass:
                    raise ValueError("Unlock this PDF before uploading it.")
                if len(pdf) > self.max_pages:
                    raise ValueError(f"Maximum {self.max_pages} PDF pages per upload.")
                for number, page in enumerate(pdf, 1):
                    text = page.get_text(sort=True).strip()
                    method = "native_pdf"
                    if len(text) < 30:
                        if page.rect.width * page.rect.height * 4 > 30_000_000:
                            raise ValueError("PDF page is too large to rasterize safely.")
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                        text = self.ocr(Image.open(io.BytesIO(pix.tobytes("png"))))
                        method = self.backend
                    pages.append({"page": number, "text": text, "method": method})
            return pages
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
            with Image.open(io.BytesIO(content)) as image:
                return [{"page": 1, "text": self.ocr(image), "method": self.backend}]
        raise ValueError("Supported files: PDF, DOC, DOCX, TXT, MD, PNG, JPG, WEBP and TIFF.")
