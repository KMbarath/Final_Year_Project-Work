import re
from datetime import datetime

DATE = r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{1,2}[ -][A-Za-z]{3,9}[ ,/-]+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
FIELDS = {
    "name": r"(?:full name|holder name|patient name|insured name|name)\s*[:\-]\s*([^\n;]+)",
    "date_of_birth": r"(?:date of birth|dob)\s*[:\-]?\s*("+DATE+r")",
    "expiry_date": r"(?:expiry date|expiration date|expire date|date of expiry|due date|expires(?: on)?|valid (?:until|till|through|thru|to)|policy end date|expiry|expiration)\s*[:\-]?\s*("+DATE+r")",
    "issue_date": r"(?:issue date|date of issue|issued on)\s*[:\-]?\s*("+DATE+r")",
    "document_number": r"(?:passport (?:no\.?|number)|pan(?: number)?|aadhaar(?: number)?|policy (?:no\.?|number)|document number|invoice number|registration (?:no\.?|number)|roll (?:no\.?|number)|patient id)\s*[:\-]\s*([A-Za-z0-9 /\-]+)",
    "email": r"(?:e-?mail(?: address)?)\s*[:\-]\s*([^\s;]+@[^\s;]+)",
    "phone": r"(?:phone|mobile|telephone)(?: number)?\s*[:\-]\s*([+\d][\d ()-]{6,20})",
    "amount": r"(?:total amount|amount due|sum insured|premium paid|subtotal)\s*[:\-]\s*([^\n;]+)",
    "address": r"address\s*[:\-]\s*([^\n;]+)",
    "owner": r"owner\s*[:\-]\s*([^\n;]+)",
    "hospital_name": r"hospital name\s*[:\-]\s*([^\n;]+)",
    "property_details": r"property details\s*[:\-]\s*([^\n;]+)",
}

PAN_NUMBER = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I)
AADHAAR_NUMBER = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")
PAN_SIGNALS = re.compile(r"income\s+tax\s+department|permanent\s+account\s+number", re.I)


def parse_date(value):
    value = re.sub(r"\s+", " ", value.strip().rstrip("."))
    for fmt in ("%Y-%m-%d","%Y/%m/%d","%Y.%m.%d","%d-%m-%Y","%d/%m/%Y","%d.%m.%Y",
                "%d %B %Y","%d %b %Y","%d-%B-%Y","%d-%b-%Y","%B %d, %Y","%b %d, %Y","%B %d %Y","%b %d %Y"):
        try:return datetime.strptime(value,fmt).date().isoformat()
        except ValueError:pass
    return None


class EntityExtractor:
    def __init__(self,model_name=""):
        self.model_name,self._model=model_name,None

    def extract(self,text):
        entities=[]
        unset = object()

        def add(label, value, start, method, normalized=unset):
            value = value.strip()
            if not value or any(e["label"] == label and e["text"].lower() == value.lower() for e in entities):
                return
            entities.append({"label": label, "text": value, "start": start,
                             "end": start + len(value), "method": method,
                             "normalized": value if normalized is unset else normalized})

        for label,pattern in FIELDS.items():
            # Dates can follow prose labels inline; names/numbers remain field-anchored.
            prefix=r"\b" if "date" in label or "birth" in label else r"(?:^|[;\n])\s*"
            for match in re.finditer(prefix+pattern,text,re.I|re.M):
                value=match.group(1).strip()
                normalized=parse_date(value) if "date" in label or "birth" in label else value
                add(label, value, match.start(1), "labelled_field", normalized)

        # Some official cards print identifiers and DOB as layout fields rather
        # than ``Label: value``.  These strict formats are safe to recognise
        # directly and avoid inventing a value from partial OCR.
        for match in PAN_NUMBER.finditer(text):
            add("document_number", match.group(), match.start(), "identifier_pattern")
        for match in AADHAAR_NUMBER.finditer(text):
            add("document_number", match.group(), match.start(), "identifier_pattern",
                re.sub(r"\D", "", match.group()))
        if PAN_SIGNALS.search(text):
            dates = list(re.finditer(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}\b", text))
            if len(dates) == 1:
                value = dates[0].group()
                add("date_of_birth", value, dates[0].start(), "pan_card_layout", parse_date(value))
        if self.model_name:
            from gliner import GLiNER
            if self._model is None:self._model=GLiNER.from_pretrained(self.model_name)
            for item in self._model.predict_entities(text[:12000],["name","date of birth","expiry date","document number"],threshold=0.65):
                label=item["label"].replace(" ","_")
                if not any(e["label"]==label for e in entities):
                    entities.append({"label":label,"text":item["text"],"start":item["start"],"end":item["end"],
                                     "method":"gliner","score":float(item["score"]),
                                     "normalized":parse_date(item["text"]) if "date" in label else item["text"]})
        return entities
