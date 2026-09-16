"""Offline integration smoke test for downloaded local models."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

ROOT=Path(__file__).resolve().parents[1]
os.environ["HF_HOME"]=str(ROOT/".cache/huggingface")
os.environ["HF_HUB_OFFLINE"]="1"
os.environ["TRANSFORMERS_OFFLINE"]="1"
from folio.config import Settings
from folio.service import Assistant
from folio.voice import Voice
from folio.classification import Classifier
from training.evaluate import SAMPLES,QUERIES,edit_distance

output=ROOT/"artifacts/optional"
output.mkdir(parents=True,exist_ok=True)
report={}
with TemporaryDirectory() as temp:
    settings=Settings(data_dir=Path(temp),embedding_model="BAAI/bge-small-en-v1.5",
                      piper_model=str(ROOT/"artifacts/voices/en_US-lessac-medium.onnx"))
    service=Assistant(settings)
    ids={label:service.ingest(text.encode(),label+".txt")["id"] for label,text in SAMPLES.items()}
    records=[]
    for question,label in QUERIES:
        hits=service.retriever.search(question,service.store.list())
        records.append({"question":question,"expected":label,"retrieved":hits[0]["filename"] if hits else None,
                        "correct":bool(hits) and hits[0]["document_id"]==ids[label]})
    report["hybrid_retrieval"]={"model":settings.embedding_model,"recall_at_1":sum(r["correct"] for r in records)/len(records),"queries":records}
    print("Hybrid retrieval tested.",flush=True)
    classifier=Classifier(ROOT/"artifacts/minilm","transformer")
    report["minilm_inference"]=classifier.predict(SAMPLES["passport"])
    assert report["minilm_inference"]["label"]=="passport"
    text="When does my passport expire?"
    audio=service.voice.synthesize(text)
    (output/"voice_question.wav").write_bytes(audio)
    assert audio[:4]==b"RIFF"
    print("Piper synthesis tested.",flush=True)
    start=time.time()
    transcript=service.voice.transcribe(audio,".wav")
    normalize=lambda t: "".join(c for c in t.lower() if c.isalnum() or c.isspace()).split()
    report["voice_roundtrip"]={"reference":text,"transcript":transcript,
                              "wer":edit_distance(normalize(text),normalize(transcript))/len(normalize(text)),
                              "seconds":time.time()-start,"wav_bytes":len(audio)}
    print("Whisper transcription:",transcript,flush=True)
report["metrics"]={"hybrid_retrieval_recall_at_1":report["hybrid_retrieval"]["recall_at_1"],
                   "synthetic_voice_roundtrip_wer":report["voice_roundtrip"]["wer"]}
report["warning"]="Smoke tests on synthetic fixtures and one synthesized voice sample; no real-world speech or semantic-search accuracy claim."
(output/"report.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
