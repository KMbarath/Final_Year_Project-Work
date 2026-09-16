from folio.facts import field_answer, is_feedback


def doc(text):
    return {"id":"one","filename":"insurance.txt","pages":[{"page":1,"text":text}]}


def test_direct_name_and_citation():
    result=field_answer("name of the user",[doc("Health insurance\nInsured name: Dev Patel\nPolicy number: INS7654321")])
    assert result["answer"] == "Insured name: Dev Patel. [1]"
    assert result["sources"][0]["page"] == 1
    assert "Policy number" not in result["answer"]


def test_missing_ambiguous_and_scoped_fields():
    assert field_answer("name",[doc("No labelled name here")])["mode"] == "abstained"
    assert "multiple values" in field_answer("name",[doc("Name: A\nName: B")])["answer"]
    assert field_answer("name",[doc("Name: A"),doc("Name: B")])["mode"] == "clarification"
    assert field_answer("father name",[doc("Name: A")]) is None


def test_amount_and_feedback():
    result=field_answer("premium paid",[doc("Sum insured: INR 500000\nPremium paid: INR 12000")])
    assert "12000" in result["answer"] and "500000" not in result["answer"]
    assert is_feedback("not satisfied")
    assert not is_feedback("what is the expiry date?")
