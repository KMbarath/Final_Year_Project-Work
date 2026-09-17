"""Conservative, cited answers for explicitly requested document fields."""
import re
from .metadata import EntityExtractor

def field_answer(question, documents):
    q = question.lower()
    # Only direct field questions; comparisons/third-party roles need retrieval.
    if re.search(r"\b(father|mother|nominee|compare|why|how|difference)\b", q):
        return None
    labels = []
    for label, pattern in [
        ("name", r"\bname\b|\bwho is (?:the )?(?:holder|insured|patient|owner)\b"),
        ("expiry_date", r"\b(expir\w*|valid until|valid till|policy end)\b"),
        ("date_of_birth", r"\b(birth|dob|born)\b"),
        ("issue_date", r"\b(issue date|date of issue|issued on)\b|\bwhen was .{0,40} issued\b"),
        ("document_number", r"\b(?:pan|aadhaar|gstin|policy|passport|document|registration|invoice|roll)\s+(?:number|no|id)\b"),
        ("email", r"\bemail\b"), ("phone", r"\b(phone|mobile|telephone)\b"),
        ("amount", r"\b(amount|premium|sum insured|subtotal)\b"),
    ]:
        if re.search(pattern, q):
            labels.append(label)
    if not labels:
        return None
    if len(documents) > 1:
        return {"answer": "Select a document so I can identify the right details.", "sources": [], "mode": "clarification"}
    if not documents:
        return {"answer": "Upload a document first so I can look up that detail.", "sources": [], "mode": "abstained"}
    doc = documents[0]
    lines, sources = [], []
    for label in labels:
        found = []
        stored = doc.get("entities") or []
        candidates = stored if stored else [e for page in doc["pages"] for e in EntityExtractor().extract(page["text"])]
        for entity in candidates:
                page = next((p for p in doc["pages"] if entity.get("text", "") in p["text"]), doc["pages"][0])
                if entity["label"] != label:
                    continue
                value = entity.get("normalized")
                if not value:
                    continue
                # Preserve the original label (e.g. insured name / premium paid).
                start = page["text"].find(entity.get("text", ""))
                line_start = page["text"].rfind("\n", 0, max(start, 0)) + 1
                caption = page["text"][line_start:start].strip().rstrip(":- ") if start >= 0 else ""
                if label == "amount" and any(w in q for w in ("premium", "sum insured", "subtotal")):
                    if not any(w in q and w in caption.lower() for w in ("premium", "sum insured", "subtotal")):
                        continue
                if value in [item[0] for item in found]:
                    continue
                found.append((value, caption or label.replace("_", " ").title(), page))
        if not found:
            lines.append("I couldn't find a labelled " + label.replace("_", " ") + " in this document.")
        else:
            if len(found) > 1 and label != "amount":
                lines.append("The document contains multiple values; I can't identify a single " + label.replace("_", " ") + ":")
            for value, caption, page in found:
                number = len(sources) + 1
                lines.append(f"{caption}: {value}. [{number}]")
                sources.append({"id": f"{doc['id']}:{page['page']}:field:{number}",
                                "document_id": doc["id"], "filename": doc["filename"],
                                "page": page["page"], "text": page["text"], "source_number": number})
    return {"answer": "\n".join(lines), "sources": sources, "mode": "document_fields" if sources else "abstained"}


def is_feedback(question):
    return re.fullmatch(r"(?:i(?: am|'m) )?(?:not satisfied|not helpful|wrong|incorrect|try again|that is wrong|that's wrong)[.! ]*", question.strip(), re.I) is not None
