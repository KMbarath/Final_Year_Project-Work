"""Deterministic filing categories for the personal document vault."""

CATEGORY_LABELS = {
    "aadhaar": "Aadhaar",
    "passport": "Passport",
    "driving_licence": "Driving licence",
    "pan": "PAN",
    "insurance": "Insurance",
    "medical": "Medical",
    "invoice": "Invoices",
    "education": "Education",
    "banking": "Banking",
    "property": "Property",
    "other": "Other documents",
}


def categorize(text: str, document_type: str = "", classifier_label: str = "") -> str:
    """File documents from explicit keywords before considering model suggestions."""
    value = " ".join((text[:30000], document_type, classifier_label)).lower()
    aadhaar_signals = ("aadhaar" in value or "uidai" in value or "unique identification authority" in value or
                       ("government of india" in value and "year of birth" in value and
                        any(marker in value for marker in ("male", "female", "gender"))))
    if aadhaar_signals:
        return "aadhaar"
    if "passport" in value:
        return "passport"
    if any(term in value for term in ("driving licence", "driving license", "driver licence", "driver license", "transport department")):
        return "driving_licence"
    if any(term in value for term in ("permanent account number", "income tax department", "pan number")):
        return "pan"
    if any(term in value for term in ("insurance", "policy number", "sum insured", "premium paid")):
        return "insurance"
    if any(term in value for term in ("medical report", "patient id", "diagnosis", "hospital", "pathology")):
        return "medical"
    if any(term in value for term in ("invoice", "gstin", "subtotal", "amount due")):
        return "invoice"
    if any(term in value for term in ("degree certificate", "mark sheet", "marksheet", "semester", "university", "school")):
        return "education"
    if any(term in value for term in ("bank statement", "account number", "ifsc", "bank of")):
        return "banking"
    if any(term in value for term in ("property deed", "sale deed", "encumbrance", "land record", "property tax")):
        return "property"
    return "other"
