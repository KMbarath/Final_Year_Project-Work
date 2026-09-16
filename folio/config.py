from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("FOLIO_DATA_DIR", str(ROOT / "data/private"))))
    classifier_path: Path = field(default_factory=lambda: Path(os.getenv("FOLIO_CLASSIFIER", str(ROOT / "artifacts/baseline/model.joblib"))))
    classifier_backend: str = field(default_factory=lambda: os.getenv("FOLIO_CLASSIFIER_BACKEND", "baseline"))
    embedding_model: str = field(default_factory=lambda: os.getenv("FOLIO_EMBEDDING_MODEL", ""))
    entity_model: str = field(default_factory=lambda: os.getenv("FOLIO_ENTITY_MODEL", ""))
    ocr_backend: str = field(default_factory=lambda: os.getenv("FOLIO_OCR", "tesseract"))
    ollama_model: str = field(default_factory=lambda: os.getenv("FOLIO_OLLAMA_MODEL", ""))
    ollama_url: str = "http://127.0.0.1:11434"
    whisper_model: str = field(default_factory=lambda: os.getenv("FOLIO_WHISPER_MODEL", "base"))
    piper_model: str = field(default_factory=lambda: os.getenv("FOLIO_PIPER_MODEL", ""))
    translation_model: str = field(default_factory=lambda: os.getenv("FOLIO_TRANSLATION_MODEL", ""))
    smtp_host: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_HOST",""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("FOLIO_SMTP_PORT","587")))
    smtp_username: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_USERNAME",""))
    smtp_password: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_PASSWORD",""))
    smtp_from: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_FROM",""))
    smtp_security: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_SECURITY","starttls"))
    public_url: str = field(default_factory=lambda: os.getenv("FOLIO_PUBLIC_URL","http://127.0.0.1:8000"))
    secure_cookies: bool = field(default_factory=lambda: os.getenv("FOLIO_SECURE_COOKIES","0")=="1")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 80

    def prepare(self):
        if self.smtp_security not in {"starttls","ssl"}:
            raise ValueError("SMTP security must be starttls or ssl.")
        self.data_dir.mkdir(parents=True, exist_ok=True)
