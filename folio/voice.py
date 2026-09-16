import io
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
        if not self.settings.translation_model:
            raise FeatureUnavailable("Configure FOLIO_TRANSLATION_MODEL with an IndicTrans2 model.")
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
