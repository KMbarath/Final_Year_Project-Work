"""Inspect local capability readiness without downloading any model."""
import importlib.util
from pathlib import Path
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from folio.config import Settings

s=Settings()
report={
    "python":sys.version.split()[0],
    "baseline_checkpoint":(ROOT/"artifacts/baseline/model.joblib").exists(),
    "minilm_checkpoint":(ROOT/"artifacts/minilm/model.safetensors").exists(),
    "tesseract":bool(shutil.which("tesseract")),
    "bge_small_cache":(ROOT/".cache/huggingface/hub/models--BAAI--bge-small-en-v1.5").exists(),
    "whisper_base":(ROOT/".cache/whisper/base.pt").exists(),
    "piper_voice":(ROOT/"artifacts/voices/en_US-lessac-medium.onnx").exists(),
    "ffmpeg_decoder":bool(shutil.which("ffmpeg")) or bool(importlib.util.find_spec("imageio_ffmpeg")),
    "ollama_executable":bool(shutil.which("ollama")),
    "optional_packages":{m:bool(importlib.util.find_spec(m)) for m in ["paddleocr","gliner","sentence_transformers","faiss","whisper","piper","IndicTransToolkit"]},
    "notebook":(ROOT/"notebooks/model_training.ipynb").exists(),
    "executed_notebook":(ROOT/"notebooks/model_training.executed.ipynb").exists(),
}
print(json.dumps(report,indent=2))
