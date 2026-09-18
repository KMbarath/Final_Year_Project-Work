from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


def default_public_url():
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
    return "https://" + render_host if render_host else "http://127.0.0.1:8000"


def default_allowed_hosts():
    return os.getenv("RENDER_EXTERNAL_HOSTNAME", "127.0.0.1,localhost,::1,testserver")


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("FOLIO_DATA_DIR", str(ROOT / "data/private"))))
    classifier_path: Path = field(default_factory=lambda: Path(os.getenv("FOLIO_CLASSIFIER", str(ROOT / "artifacts/baseline/model.joblib"))))
    classifier_backend: str = field(default_factory=lambda: os.getenv("FOLIO_CLASSIFIER_BACKEND", "baseline"))
    embedding_model: str = field(default_factory=lambda: os.getenv("FOLIO_EMBEDDING_MODEL", ""))
    entity_model: str = field(default_factory=lambda: os.getenv("FOLIO_ENTITY_MODEL", ""))
    ocr_backend: str = field(default_factory=lambda: os.getenv("FOLIO_OCR", "tesseract"))
    ollama_model: str = field(default_factory=lambda: os.getenv("FOLIO_OLLAMA_MODEL", ""))
    extraction_model: str = field(default_factory=lambda: os.getenv("FOLIO_EXTRACTION_MODEL", os.getenv("FOLIO_OLLAMA_MODEL", "")))
    ollama_url: str = field(default_factory=lambda: os.getenv("FOLIO_OLLAMA_URL", ""))
    prompts_path: Path = field(default_factory=lambda: Path(os.getenv("FOLIO_PROMPTS_PATH", str(ROOT / "prompts.yaml"))))
    whisper_model: str = field(default_factory=lambda: os.getenv("FOLIO_WHISPER_MODEL", "base"))
    piper_model: str = field(default_factory=lambda: os.getenv("FOLIO_PIPER_MODEL", ""))
    translation_model: str = field(default_factory=lambda: os.getenv("FOLIO_TRANSLATION_MODEL", ""))
    # Google is the default deployed translation adapter. Set this variable to
    # an empty value only when translated answers must be disabled entirely.
    translation_provider: str = field(default_factory=lambda: os.getenv("FOLIO_TRANSLATION_PROVIDER", "google"))
    smtp_host: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_HOST",""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("FOLIO_SMTP_PORT","587")))
    smtp_username: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_USERNAME",""))
    smtp_password: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_PASSWORD",""))
    smtp_from: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_FROM",""))
    smtp_security: str = field(default_factory=lambda: os.getenv("FOLIO_SMTP_SECURITY","starttls"))
    public_url: str = field(default_factory=lambda: os.getenv("FOLIO_PUBLIC_URL", default_public_url()))
    secure_cookies: bool = field(default_factory=lambda: os.getenv("FOLIO_SECURE_COOKIES","0")=="1")
    require_models: bool = field(default_factory=lambda: os.getenv("FOLIO_REQUIRE_MODELS", "0") == "1")
    allowed_hosts: tuple[str, ...] = field(default_factory=lambda: tuple(host.strip() for host in os.getenv(
        "FOLIO_ALLOWED_HOSTS", default_allowed_hosts()).split(",") if host.strip()))
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 80

    def prepare(self):
        if self.smtp_security not in {"starttls","ssl"}:
            raise ValueError("SMTP security must be starttls or ssl.")
        if self.translation_provider not in {"", "google"}:
            raise ValueError("FOLIO_TRANSLATION_PROVIDER must be google or blank.")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.require_models and (not self.ollama_model or not self.extraction_model or not self.embedding_model):
            raise ValueError("FOLIO_REQUIRE_MODELS=1 requires answer, extraction, and embedding models.")
