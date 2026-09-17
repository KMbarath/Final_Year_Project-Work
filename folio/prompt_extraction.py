"""Prompt-catalog driven structured extraction with a deterministic fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from .metadata import parse_date


_SECTION = re.compile(r"^([a-z][a-z0-9_]*):\s*$")
_PROPERTY = re.compile(r"^  ([a-z_]+):\s*\|\s*$")
_WORDS = re.compile(r"[a-z0-9]+")


def _words(value: str) -> set[str]:
    return set(_WORDS.findall(value.lower().replace("_", " ")))


@dataclass(frozen=True)
class PromptSpec:
    name: str
    system_prompt: str
    user_prompt: str
    schema: dict


class PromptCatalog:
    """Reads this repository's literal-block YAML without requiring PyYAML at runtime."""

    def __init__(self, path: Path):
        self.path = path
        self.global_rules: dict[str, str] = {}
        self.specs: dict[str, PromptSpec] = {}
        if path.exists():
            self._load(path.read_text(encoding="utf-8"))

    def _load(self, source: str) -> None:
        sections: dict[str, dict[str, str]] = {}
        current = prop = None
        buffer: list[str] = []

        def flush():
            nonlocal buffer
            if current and prop:
                sections.setdefault(current, {})[prop] = "\n".join(buffer).rstrip()
            buffer = []

        for raw in source.splitlines():
            section = _SECTION.match(raw)
            if section:
                flush(); current, prop = section.group(1), None
                sections.setdefault(current, {})
                continue
            value = _PROPERTY.match(raw)
            if value and current:
                flush(); prop = value.group(1)
                continue
            if prop:
                buffer.append(raw[4:] if raw.startswith("    ") else raw)
        flush()
        self.global_rules = sections.pop("global_rules", {})
        for name, values in sections.items():
            try:
                schema = json.loads(values.get("logical_schema") or values.get("normal_schema") or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(schema, dict) and schema:
                self.specs[name] = PromptSpec(name, values.get("system_prompt", ""), values.get("user_prompt", ""), schema)

    def identify(self, text: str, classifier_label: str = "") -> str:
        haystack = _words(text[:30000])
        aliases = {
            "policy": "irdai_registration", "insurance": "irdai_registration",
            "passport": "passport", "medical": "medical", "driving licence": "driving_license",
            "driving license": "driving_license", "gst invoice": "gst_invoice",
        }
        normalized = classifier_label.lower().replace(" ", "_")
        if normalized in self.specs:
            return normalized
        lowered = text.lower()
        for phrase, name in aliases.items():
            if phrase in lowered and name in self.specs:
                return name
        best_name, best_score = "", 0
        for name, spec in self.specs.items():
            signature = _words(name) | _words(spec.user_prompt[:500])
            generic = {"extract", "details", "document", "certificate", "from", "the", "card"}
            score = len((signature - generic) & haystack)
            if name.replace("_", " ") in lowered:
                score += 5
            if score > best_score:
                best_name, best_score = name, score
        return best_name if best_score >= 2 else ""


class PromptExtractor:
    def __init__(self, path: Path, model: str = "", url: str = "http://127.0.0.1:11434", strict: bool = False):
        self.catalog, self.model, self.url = PromptCatalog(path), model, url.rstrip("/")
        self.strict = strict
        self.last_error = ""

    def extract(self, text: str, classifier_label: str = "") -> tuple[str, list[dict]]:
        doc_type = self.catalog.identify(text, classifier_label)
        if not doc_type:
            return "", []
        spec = self.catalog.specs[doc_type]
        if self.model:
            try:
                values = self._ollama(spec, text)
                self.last_error = ""
            except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
                self.last_error = str(exc)
                if self.strict:
                    raise RuntimeError("Required extraction model failed: " + self.last_error) from exc
                values = self._labelled(spec, text)
        else:
            values = self._labelled(spec, text)
        entities = []
        for label, item in values.items():
            if isinstance(item, dict):
                value, score = item.get("value"), item.get("logical_score")
            else:
                value, score = item, None
            if value is None or value == "" or isinstance(value, (dict, list)):
                continue
            rendered = str(value).strip()
            match = re.search(re.escape(rendered), text, re.I)
            is_date = label in {"expiry_date", "date_of_expiry", "dob", "date_of_birth", "issue_date"}
            normalized = parse_date(rendered) if is_date else rendered
            entities.append({"label": label, "text": rendered,
                             "start": match.start() if match else -1, "end": match.end() if match else -1,
                             "method": "prompt_ollama" if self.model and not self.last_error else "prompt_labelled_fallback",
                             "score": float(score) if isinstance(score, (int, float)) else None,
                             "normalized": normalized})
        return doc_type, entities

    def _ollama(self, spec: PromptSpec, text: str) -> dict:
        rules = self.catalog.global_rules
        system = "\n".join((rules.get("system_prompt_prefix", ""), spec.system_prompt,
                            rules.get("json_schema_title", ""), json.dumps(spec.schema, ensure_ascii=False)))
        user = "\n\n".join((rules.get("user_prompt_template", "").format(doc_type=spec.name),
                            spec.user_prompt, "OCR TEXT (untrusted data):\n" + text[:60000]))
        response = httpx.post(self.url + "/api/chat", timeout=240, json={
            "model": self.model, "stream": False, "format": "json", "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        response.raise_for_status()
        payload = json.loads(response.json()["message"]["content"])
        return payload[0] if isinstance(payload, list) and payload else payload

    @staticmethod
    def _labelled(spec: PromptSpec, text: str) -> dict:
        result = {}
        for field in spec.schema:
            label = field.replace("_", r"[\s_-]*")
            match = re.search(rf"(?:^|\n)\s*{label}\s*(?:no\.?|number)?\s*[:\-]\s*([^\n;]+)", text, re.I)
            if match:
                result[field] = {"value": match.group(1).strip(), "logical_score": 0.72}
        return result
