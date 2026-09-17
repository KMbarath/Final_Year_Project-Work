"""Page-preserving chunking, BM25, optional BGE-M3 + FAISS, rank fusion."""
import re
import math
from collections import Counter
import numpy as np
from .model_cache import cached_model_path

STOP = set("the a an is are was were my me i what when where does do of to in on for and please tell show document documents".split())
ALIASES = {"expire": "expiry", "expires": "expiry", "expiration": "expiry", "born": "birth", "dob": "birth", "no": "number"}


def tokens(text):
    return [ALIASES.get(t, t) for t in re.findall(r"\w+", text.lower()) if t not in STOP]


def chunk_pages(document, size=240, overlap=40):
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must exceed nonnegative overlap.")
    chunks = []
    facts = []
    for entity in document.get("entities", []):
        value = entity.get("normalized") or entity.get("text")
        if value:
            facts.append(f"{entity['label'].replace('_', ' ')}: {value}")
    if facts:
        chunks.append({"id": f"{document['id']}:facts", "document_id": document["id"],
                       "filename": document["filename"], "page": 1,
                       "text": "Structured extracted facts. " + "; ".join(facts), "kind": "structured_facts"})
    for page in document["pages"]:
        words = page["text"].split()
        for start in range(0, len(words), size - overlap):
            chunks.append({"id": f"{document['id']}:{page['page']}:{start}",
                           "document_id": document["id"], "filename": document["filename"],
                           "page": page["page"], "text": " ".join(words[start:start + size]), "kind": "page_text"})
            if start + size >= len(words):
                break
    return chunks


class Retriever:
    def __init__(self, model_name=""):
        self.model_name, self._encoder, self._cache_key = model_name, None, None

    def search(self, question, documents, k=5):
        chunks = [c for doc in documents for c in chunk_pages(doc)]
        if not chunks:
            return []
        bags = [Counter(tokens(c["text"])) for c in chunks]
        lengths = np.array([sum(b.values()) for b in bags])
        avg = max(float(lengths.mean()), 1)
        scores = np.zeros(len(chunks))
        vocabulary = set().union(*(bag.keys() for bag in bags))
        for term in set(tokens(question)):
            matches = [candidate for candidate in vocabulary if candidate == term or candidate.startswith(term)]
            for matched_term in matches:
                frequency = sum(matched_term in b for b in bags)
                idf = math.log(1 + (len(chunks) - frequency + 0.5) / (frequency + 0.5))
                tf = np.array([b[matched_term] for b in bags])
                scores += idf * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * lengths / avg))
        for i, chunk in enumerate(chunks):
            if chunk.get("kind") == "structured_facts":
                scores[i] *= 1.35
        order = [int(i) for i in np.argsort(-scores) if scores[i] > 0]
        fused = {i: 1 / (60 + rank) for rank, i in enumerate(order, 1)}
        semantic = {}
        if self.model_name == "lsa":
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from sklearn.preprocessing import normalize
            key = tuple((c["id"], c["text"]) for c in chunks)
            if key != self._cache_key:
                self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
                sparse = self._vectorizer.fit_transform([c["text"] for c in chunks])
                dimensions = min(128, sparse.shape[0] - 1, sparse.shape[1] - 1)
                self._lsa = TruncatedSVD(dimensions, random_state=42) if dimensions >= 2 else None
                self._vectors = normalize(self._lsa.fit_transform(sparse) if self._lsa else sparse).astype("float32")
                self._cache_key = key
            query_sparse = self._vectorizer.transform([question])
            query_vector = normalize(self._lsa.transform(query_sparse) if self._lsa else query_sparse).astype("float32")
            similarities = (self._vectors @ query_vector.T).toarray().ravel() if hasattr(self._vectors @ query_vector.T, "toarray") else np.asarray(self._vectors @ query_vector.T).ravel()
            for rank, idx in enumerate(np.argsort(-similarities)[:max(k * 3, 20)], 1):
                similarity = float(similarities[idx])
                semantic[int(idx)] = similarity
                if similarity > 0:
                    fused[int(idx)] = fused.get(int(idx), 0) + 1 / (60 + rank)
        elif self.model_name:
            import faiss
            from sentence_transformers import SentenceTransformer
            if self._encoder is None:
                self._encoder = SentenceTransformer(cached_model_path(self.model_name), device="cpu")
            key = tuple((c["id"], c["text"]) for c in chunks)
            if key != self._cache_key:
                vectors = self._encoder.encode([c["text"] for c in chunks], normalize_embeddings=True, batch_size=4).astype("float32")
                self._index = faiss.IndexFlatIP(vectors.shape[1])
                self._index.add(vectors)
                self._cache_key = key
            vector = self._encoder.encode([question], normalize_embeddings=True).astype("float32")
            similarities, indices = self._index.search(vector, min(len(chunks), max(k * 3, 20)))
            for rank, (idx, similarity) in enumerate(zip(indices[0], similarities[0]), 1):
                idx = int(idx)
                semantic[idx] = float(similarity)
                if similarity >= 0.35:
                    fused[idx] = fused.get(idx, 0) + 1 / (60 + rank)
        ranked = sorted(fused, key=lambda i: fused[i], reverse=True)[:k]
        return [{**chunks[i], "score": fused[i], "keyword_score": float(scores[i]),
                 "semantic_score": semantic.get(i)} for i in ranked]
