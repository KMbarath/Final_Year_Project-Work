import pytest


@pytest.fixture(autouse=True)
def no_real_smtp(monkeypatch):
    # Test execution must never use a developer's live SMTP credentials.
    for key in ["FOLIO_SMTP_HOST","FOLIO_SMTP_FROM","FOLIO_SMTP_USERNAME","FOLIO_SMTP_PASSWORD"]:
        monkeypatch.delenv(key,raising=False)
