import json
from pathlib import Path


class Classifier:
    def __init__(self, path, backend="baseline"):
        self.path, self.backend = Path(path), backend
        self._model = None

    def predict(self, text):
        if not self.path.exists():
            return {"label": "unknown", "confidence": 0.0, "backend": "untrained", "needs_review": True}
        if self.backend == "transformer":
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            if self._model is None:
                self._tokenizer = AutoTokenizer.from_pretrained(self.path, local_files_only=True)
                self._model = AutoModelForSequenceClassification.from_pretrained(self.path, local_files_only=True).eval()
                meta = self.path / "folio_metadata.json"
                self._meta = json.loads(meta.read_text()) if meta.exists() else {}
            with torch.inference_mode():
                inputs = self._tokenizer(text, truncation=True, max_length=int(self._meta.get("max_length", 192)), return_tensors="pt")
                probs = self._model(**inputs).logits.softmax(-1)[0].numpy()
            index = int(probs.argmax())
            label, confidence = self._model.config.id2label[index], float(probs[index])
        else:
            import joblib
            if self._model is None:
                # Only load locally produced artifacts, never user-uploaded pickle files.
                self._model = joblib.load(self.path)
                self._meta = self._model["metadata"]
            probabilities = self._model["classifier"].predict_proba(self._model["vectorizer"].transform([text]))[0]
            index = int(probabilities.argmax())
            label, confidence = str(self._model["classifier"].classes_[index]), float(probabilities[index])
        threshold = float(self._meta.get("confidence_threshold", 0.7))
        signatures = {
            "passport": ("passport", "passport number"),
            "medical": ("medical report", "patient", "diagnosis"),
            "insurance": ("insurance", "policy number", "premium"),
            "invoice": ("invoice", "amount due", "subtotal"),
            "aadhaar": ("aadhaar", "unique identification"),
            "pan": ("pan number", "income tax"),
        }
        matched = sum(any(marker in text.lower() for marker in markers) for markers in signatures.values())
        ambiguous = matched > 1
        predicted = "unknown" if ambiguous or confidence < threshold else label
        return {"label": predicted, "suggested_label": label,
                "confidence": confidence, "backend": self.backend,
            "training_data": self._meta.get("data_kind", "unverified"), "needs_review": ambiguous or confidence < threshold}
