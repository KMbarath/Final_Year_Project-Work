from folio.metadata import EntityExtractor


EXTRACTOR = EntityExtractor()


def extract(text):
    return EXTRACTOR.extract(text)


def values(entities, label):
    return [entity["normalized"] for entity in entities if entity["label"] == label]


def test_META_001_name_extraction():
    entities = extract("Name: Jane Doe")
    assert values(entities, "name") == ["Jane Doe"]


def test_META_002_document_number():
    entities = extract("Passport number: P1234567")
    assert values(entities, "document_number") == ["P1234567"]


def test_META_003_issue_date():
    entities = extract("Issue date: 2024-01-15")
    assert values(entities, "issue_date") == ["2024-01-15"]


def test_META_004_expiry_date():
    entities = extract("Expiry date: 2035-06-01")
    assert values(entities, "expiry_date") == ["2035-06-01"]


def test_META_005_address_extraction():
    entities = extract("Address: 12 Safe Street, Pune")
    assert values(entities, "address") == ["12 Safe Street, Pune"], entities


def test_META_006_owner_extraction():
    entities = extract("Owner: Jane Doe")
    assert values(entities, "owner") == ["Jane Doe"], entities


def test_META_007_hospital_name_extraction():
    entities = extract("Hospital name: Safe General Hospital")
    assert values(entities, "hospital_name") == ["Safe General Hospital"], entities


def test_META_008_property_details_extraction():
    entities = extract("Property details: Survey Number 42, Plot 7")
    assert values(entities, "property_details") == ["Survey Number 42, Plot 7"], entities


def test_META_009_missing_metadata_does_not_hallucinate():
    entities = extract("Document type: personal note\nNo labelled metadata is present.")
    assert entities == []


def test_META_010_invalid_date_is_not_normalized():
    entities = extract("Expiry date: 31/02/2030")
    assert values(entities, "expiry_date") == [None]
    assert not any(entity["normalized"] for entity in entities)


def test_META_011_multiple_dates():
    entities = extract("Issue date: 2024-01-15\nExpiry date: 2035-06-01")
    assert values(entities, "issue_date") == ["2024-01-15"]
    assert values(entities, "expiry_date") == ["2035-06-01"]


def test_META_012_multiple_names():
    entities = extract("Name: Jane Doe\nName: John Doe")
    assert values(entities, "name") == ["Jane Doe", "John Doe"]