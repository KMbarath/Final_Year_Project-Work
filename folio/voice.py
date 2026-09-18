import io
import html
import wave
import shutil
import subprocess
import numpy as np
from .config import ROOT
from pathlib import Path
from tempfile import TemporaryDirectory
from .extraction import FeatureUnavailable

LANGUAGES = {"hi": "hin_Deva", "ta": "tam_Taml", "te": "tel_Telu", "ml": "mal_Mlym",
             "kn": "kan_Knda", "bn": "ben_Beng", "mr": "mar_Deva", "gu": "guj_Gujr",
             "pa": "pan_Guru", "or": "ory_Orya"}
MYMEMORY_LANGUAGES = {"hi": "hi-IN", "ta": "ta-IN", "te": "te-IN", "ml": "ml-IN",
                      "kn": "kn-IN", "bn": "bn-IN", "mr": "mr-IN", "gu": "gu-IN",
                      "pa": "pa-IN", "or": "or-IN"}


class Voice:
    def __init__(self, settings):
        self.settings = settings
        self._whisper = self._piper = self._translator = None

    def transcribe(self, content, suffix):
        try:
            import whisper
        except ImportError as exc:
            raise FeatureUnavailable("Install the voice extra to use Whisper.") from exc
        if self._whisper is None:
            self._whisper = whisper.load_model(self.settings.whisper_model, device="cpu", download_root=str(ROOT / ".cache/whisper"))
        with TemporaryDirectory() as folder:
            path = Path(folder) / ("question" + suffix)
            path.write_bytes(content)
            executable = shutil.which("ffmpeg")
            if not executable:
                try:
                    import imageio_ffmpeg
                    executable = imageio_ffmpeg.get_ffmpeg_exe()
                except ImportError as exc:
                    raise FeatureUnavailable("Install the voice extra for the bundled audio decoder.") from exc
            try:
                decoded = subprocess.run([executable, "-nostdin", "-threads", "1", "-i", str(path),
                                          "-t", "121", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                                         capture_output=True, check=True, timeout=60)
            except subprocess.CalledProcessError as exc:
                raise ValueError("The audio file could not be decoded.") from exc
            audio = np.frombuffer(decoded.stdout, np.int16).astype(np.float32) / 32768.0
            if len(audio) > 120 * 16000:
                raise ValueError("Audio must be at most two minutes long.")
            if len(audio) < 1600:
                raise ValueError("Audio is too short to transcribe.")
            return self._whisper.transcribe(audio, fp16=False)["text"].strip()

    def synthesize(self, text):
        if not self.settings.piper_model:
            raise FeatureUnavailable("Configure FOLIO_PIPER_MODEL with a downloaded Piper ONNX voice.")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise FeatureUnavailable("Install the voice extra to use Piper.") from exc
        if self._piper is None:
            self._piper = PiperVoice.load(self.settings.piper_model)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self._piper.synthesize_wav(text, wav)
        return buffer.getvalue()

    def translate(self, text, target):
        if target == "en":
            return text
        if target not in LANGUAGES:
            raise ValueError("Unsupported target language.")
        if self.settings.translation_provider == "mymemory":
            try:
                from deep_translator import MyMemoryTranslator
            except ImportError as exc:
                raise FeatureUnavailable("Install the translation dependency to use MyMemory.") from exc
            try:
                return MyMemoryTranslator(source="en-GB", target=MYMEMORY_LANGUAGES[target]).translate(text)
            except Exception as exc:
                raise FeatureUnavailable("The free MyMemory translation service is temporarily unavailable. Try again later.") from exc
        if self.settings.translation_provider == "google-cloud":
            return self._translate_google_cloud(text, target)
        if self.settings.translation_provider == "google":
            try:
                from deep_translator import GoogleTranslator, MyMemoryTranslator
            except ImportError as exc:
                raise FeatureUnavailable("Install the translation dependency to use the configured provider.") from exc
            # This provider performs the NLP translation remotely.  Do not hide
            # the boundary: the UI tells the user before they select a language.
            try:
                return GoogleTranslator(source="en", target=target).translate(text)
            except Exception as google_error:
                # The free Google endpoint can rate-limit. MyMemory supports the
                # same Indian-language targets and keeps language selection usable.
                try:
                    return MyMemoryTranslator(source="en-GB", target=MYMEMORY_LANGUAGES[target]).translate(text)
                except Exception as fallback_error:
                    raise FeatureUnavailable("Translation services are temporarily unavailable. Try again later.") from fallback_error
        if not self.settings.translation_model:
            raise FeatureUnavailable("Configure a translation provider or an IndicTrans2 model.")
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            from IndicTransToolkit.processor import IndicProcessor
        except ImportError as exc:
            raise FeatureUnavailable("Install the translation extra in a compatible environment.") from exc
        if self._translator is None:
            tokenizer = AutoTokenizer.from_pretrained(self.settings.translation_model, trust_remote_code=True)
            model = AutoModelForSeq2SeqLM.from_pretrained(self.settings.translation_model, trust_remote_code=True).eval()
            self._translator = tokenizer, model, IndicProcessor(inference=True)
        tokenizer, model, processor = self._translator
        processed = processor.preprocess_batch([text], src_lang="eng_Latn", tgt_lang=LANGUAGES[target])
        inputs = tokenizer(processed, return_tensors="pt", padding=True, truncation=True, max_length=512)
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=512, num_beams=4)
        decoded = tokenizer.batch_decode(output, skip_special_tokens=True)
        return processor.postprocess_batch(decoded, lang=LANGUAGES[target])[0]

    def _translate_google_cloud(self, text, target):
        if not self.settings.translation_api_key:
            raise FeatureUnavailable("Configure GOOGLE_TRANSLATE_API_KEY for the google-cloud provider.")
        try:
            import httpx
            response = httpx.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": self.settings.translation_api_key},
                json={"q": text, "source": "en", "target": target, "format": "text"},
                timeout=20,
            )
            response.raise_for_status()
            translated = response.json()["data"]["translations"][0]["translatedText"]
            return html.unescape(translated)
        except FeatureUnavailable:
            raise
        except Exception as exc:
            raise FeatureUnavailable("Google Cloud Translation is temporarily unavailable. Try again later.") from exc
