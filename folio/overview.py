"""Small conversational intents that do not require loading a retrieval model."""
import re


def is_greeting(question):
    return re.fullmatch(r"(hi|hello|hey|good (morning|afternoon|evening))[!. ]*", question.strip(), re.I) is not None


def is_overview(question):
    text = question.lower().strip().rstrip(".!?")
    text = re.sub(r"^(please\s+)", "", text)
    return re.fullmatch(
        r"(?:(?:give|write|provide)(?: me)? (?:a )?)?"
        r"(?:brief note|brief summary|short summary|summary|overview|summari[sz]e)"
        r"(?: (?:about|of|on))?(?: (?:this|the|my|selected))?"
        r"(?: (?:document|file|pdf))?", text) is not None


def overview(documents):
    if not documents:
        return {"answer": "Upload a document first, then ask me for a brief overview.", "sources": [], "mode": "abstained"}
    if len(documents) != 1:
        return {"answer": "Select a document in the dropdown so I can give you an overview of the right file.",
                "sources": [], "mode": "clarification"}
    document = documents[0]
    pages = [p for p in document["pages"] if p["text"].strip()]
    if not pages:
        return {"answer": "There is no readable text to summarize in this document.", "sources": [], "mode": "abstained"}
    # Sample the beginning, middle and end; keep quotations exact and identify partial coverage.
    indices = sorted(set([0, len(pages)//2, len(pages)-1]))
    sources, excerpts = [], []
    for index in indices:
        page = pages[index]
        text = page["text"].strip()
        match = re.search(r"\S+(?:\s+\S+){0,69}", text)
        excerpt = match.group(0)
        number = len(sources) + 1
        sources.append({"id": f"{document['id']}:{page['page']}:overview",
                        "document_id": document["id"], "filename": document["filename"],
                        "page": page["page"], "text": text, "source_number": number})
        excerpts.append(f"[{number}] {excerpt}" + (" ..." if len(excerpt) < len(text) else ""))
    count = len(document["pages"])
    return {"answer": f"{document['filename']} contains {count} page{'s' if count != 1 else ''}.\n\n"
                       "Brief overview from extracted passages:\n\n" + "\n\n".join(excerpts),
            "sources": sources, "mode": "extractive_overview",
            "note": "Selected passages, not a complete generated summary; review the source pages for full details."}
