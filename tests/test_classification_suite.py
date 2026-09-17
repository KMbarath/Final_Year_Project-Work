from pathlib import Path

from folio.classification import Classifier


CLASSIFIER = Classifier(Path("artifacts/baseline/model.joblib"))


def classify(expected, text):
    result = CLASSIFIER.predict(text)
    assert result["label"] == expected, (
        f"Expected category {expected!r}; predicted {result['label']!r}; "
        f"suggested {result.get('suggested_label')!r}; "
        f"confidence {result.get('confidence')!r}; result={result!r}"
    )
    return result


def test_CLASS_001_aadhaar_like_sample():
    result = classify(
        "aadhaar",
        "Government of India Aadhaar Unique Identification Authority of India "
        "Aadhaar Number 1234 5678 9012 Date of Birth 01/01/1990",
    )
    assert result["confidence"] >= 0.7


def test_CLASS_002_passport_like_sample():
    result = classify(
        "passport",
        "Republic of India Passport Type P Passport No P1234567 Surname DOE "
        "Given Name JANE Nationality INDIAN Date of Birth 01/01/1990 "
        "Date of Expiry 01/06/2035",
    )
    assert result["confidence"] >= 0.7


def test_CLASS_003_medical_report():
    result = classify(
        "medical",
        "Medical Report Patient Name Jane Doe Diagnosis Blood Test "
        "Hemoglobin 13.2 g/dL Doctor Signature Laboratory Results",
    )
    assert result["confidence"] >= 0.7


def test_CLASS_004_property_deed_is_unknown():
    result = classify(
        "unknown",
        "Property Deed Sale Deed Land Registry Sub Registrar Property Description "
        "Survey Number 42 Buyer and Seller Consideration Amount",
    )
    assert result["needs_review"] is True


def test_CLASS_005_degree_certificate_is_unknown():
    result = classify(
        "unknown",
        "University Degree Certificate This certifies that Jane Doe has been "
        "awarded the Bachelor of Science Degree University Registrar Graduation 2024",
    )
    assert result["needs_review"] is True


def test_CLASS_006_insurance_document():
    result = classify(
        "insurance",
        "Health Insurance Policy Policy Number INS12345 Policy Holder Jane Doe "
        "Sum Insured Premium Policy Period Expiry Date 01/06/2035",
    )
    assert result["confidence"] >= 0.7


def test_CLASS_007_unknown_document():
    result = classify(
        "unknown",
        "The quick brown fox jumps over the lazy dog. This is an unrelated "
        "personal note with no document identifiers.",
    )
    assert result["needs_review"] is True


def test_CLASS_008_poor_quality_document():
    result = classify("passport", "PASSPORT P1234567 EXPIRY 2035")
    assert result["confidence"] >= 0.7


def test_CLASS_009_multiple_document_like_sections_are_unknown():
    classify(
        "unknown",
        "PASSPORT P1234567 Name Jane Doe. Medical Report Patient Jane Doe "
        "Diagnosis Routine. Insurance Policy INS12345 Premium Paid.",
    )