from unittest.mock import Mock

import httpx
import pytest

from folio.config import Settings
from folio.extraction import FeatureUnavailable
from folio.voice import Voice


def test_google_translation_provider_uses_selected_language(monkeypatch):
    translator = Mock()
    translator.translate.return_value = "translated"
    factory = Mock(return_value=translator)
    monkeypatch.setattr("deep_translator.GoogleTranslator", factory)
    voice = Voice(Settings(translation_provider="google"))
    assert voice.translate("Document expires tomorrow.", "ta") == "translated"
    factory.assert_called_once_with(source="en", target="ta")


def test_translation_falls_back_when_google_is_rate_limited(monkeypatch):
    google = Mock()
    google.translate.side_effect = RuntimeError("rate limited")
    memory = Mock()
    memory.translate.return_value = "fallback translation"
    monkeypatch.setattr("deep_translator.GoogleTranslator", Mock(return_value=google))
    memory_factory = Mock(return_value=memory)
    monkeypatch.setattr("deep_translator.MyMemoryTranslator", memory_factory)
    assert Voice(Settings(translation_provider="google")).translate("Hello", "ta") == "fallback translation"
    memory_factory.assert_called_once_with(source="en-GB", target="ta-IN")


def test_google_cloud_translation_uses_api_key(monkeypatch):
    response = Mock()
    response.json.return_value = {"data": {"translations": [{"translatedText": "வணக்கம்"}]}}
    response.raise_for_status.return_value = None
    request = Mock(return_value=response)
    monkeypatch.setattr("httpx.post", request)

    result = Voice(Settings(translation_provider="google-cloud", translation_api_key="secret")).translate("Hello", "ta")

    assert result == "வணக்கம்"
    request.assert_called_once_with(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": "secret"},
        json={"q": "Hello", "source": "en", "target": "ta", "format": "text"},
        timeout=20,
    )


def test_google_cloud_translation_requires_api_key():
    with pytest.raises(FeatureUnavailable, match="GOOGLE_TRANSLATE_API_KEY"):
        Voice(Settings(translation_provider="google-cloud")).translate("Hello", "ta")
