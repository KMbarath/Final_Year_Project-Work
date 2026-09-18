from unittest.mock import Mock

from folio.config import Settings
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
