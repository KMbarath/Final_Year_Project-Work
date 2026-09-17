import hashlib
import threading
import uuid
from pathlib import PureWindowsPath
from .storage import Store
from .extraction import Extractor
from .classification import Classifier
from .metadata import EntityExtractor
from .retrieval import Retriever
from .answering import answer
from .voice import Voice
from .facts import field_answer, is_feedback
from .overview import is_greeting, is_overview, overview
from .prompt_extraction import PromptExtractor


class Assistant:
    def __init__(self, settings):
        settings.prepare()
        self.settings = settings
        self.store = Store(settings.data_dir)
        self.extractor = Extractor(settings.ocr_backend, settings.max_pages)
        self.classifier = Classifier(settings.classifier_path, settings.classifier_backend)
        self.entities = EntityExtractor(settings.entity_model)
        self.prompt_extractor = PromptExtractor(settings.prompts_path, settings.extraction_model, settings.ollama_url, settings.require_models)
        self.retriever = Retriever(settings.embedding_model)
        self.voice = Voice(settings)
        self.lock = threading.RLock()

    def ingest(self, content, filename, owner_id=None):
        if not content or len(content) > self.settings.max_upload_bytes:
            raise ValueError("Upload must be nonempty and at most 20 MB.")
        digest = hashlib.sha256((owner_id or "").encode()+content).hexdigest()
        with self.lock:
            existing = self.store.by_digest(digest,owner_id)
            if existing:
                return {**existing, "duplicate": True}
            pages = self.extractor.extract(content, filename)
            text = "\n".join(p["text"] for p in pages)
            if len(text.strip()) < 5:
                raise ValueError("No readable text was found. Try a clearer scan.")
            classification = self.classifier.predict(text)
            entities = self.entities.extract(text)
            document_type, prompt_entities = self.prompt_extractor.extract(text, classification.get("label", ""))
            existing = {(e["label"], str(e.get("normalized", "")).lower()) for e in entities}
            entities.extend(e for e in prompt_entities if (e["label"], str(e.get("normalized", "")).lower()) not in existing)
            dates = {e["normalized"] for e in entities if e["label"] == "expiry_date" and e["normalized"]}
            expiry = next(iter(dates)) if len(dates)==1 else None
            return self.store.add({"id": uuid.uuid4().hex, "filename": PureWindowsPath(filename).name[:200],
                                   "owner_id": owner_id, "digest": digest, "content": content, "pages": pages, "entities": entities, "expiry_date": expiry,
                                   "document_type": document_type or classification.get("label", "unknown"),
                                   "classification": classification})

    def ask(self, question, document_id=None, language="en", owner_id=None, history=None):
        if is_greeting(question):
            return {"answer": "Hello! Select a document and ask for a brief overview, or ask about a specific detail.",
                    "sources": [], "mode": "greeting", "language": "en"}
        if is_feedback(question):
            return {"answer": "Sorry that didn't answer your question. Which detail should I clarify: the name, expiry date, document number, or something else?", "sources": [], "mode": "clarification", "language": "en"}
        with self.lock:
            documents = self.store.list(owner_id)
            if document_id:
                documents = [d for d in documents if d["id"] == document_id]
                if not documents:
                    raise ValueError("Selected document no longer exists.")
            direct = field_answer(question, documents)
            if direct is not None:
                result = direct
            elif is_overview(question):
                result = overview(documents)
            else:
                retrieval_question = question
                if history and len(question.split()) < 12 and any(w in question.lower().split() for w in ["it","its","that","this","they","their"]):
                    previous = next((m["content"] for m in reversed(history) if m["role"]=="user"),"")
                    retrieval_question = previous + " " + question
                hits = self.retriever.search(retrieval_question, documents)
                result = answer(question, hits, self.settings.ollama_model, self.settings.ollama_url,history=history)
            if language != "en":
                result["original_answer"] = result["answer"]
                result["answer"] = self.voice.translate(result["answer"], language)
            result["language"] = language
            return result

    def transcribe(self, content, suffix):
        with self.lock:
            return self.voice.transcribe(content, suffix)
