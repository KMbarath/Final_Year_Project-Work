import json
import types
import sys
from unittest.mock import Mock
import pytest
from PIL import Image
from folio.answering import answer
from folio.extraction import Extractor
from folio.metadata import EntityExtractor
from folio.voice import Voice
from folio.config import Settings
from folio.retrieval import Retriever

HITS=[{"document_id":"abc","filename":"passport.txt","page":1,"text":"Expiry: 2032-06-10"}]


def test_llm_context_is_untrusted_and_sources_are_validated(monkeypatch):
    response=Mock()
    response.json.return_value={"message":{"content":json.dumps({"answer":"Expires in 2032 [1].","source_ids":[1]})}}
    post=Mock(return_value=response)
    monkeypatch.setattr("folio.answering.httpx.post",post)
    result=answer("Expiry?",HITS,model="llama3.1:8b")
    assert result["mode"]=="generated"
    assert result["sources"][0]["source_number"]==1
    payload=post.call_args.kwargs["json"]
    assert "untrusted" in payload["messages"][0]["content"]
    assert payload["messages"][1]["role"]=="user"
    response.json.return_value={"message":{"content":json.dumps({"answer":"Invented [99]","source_ids":[99]})}}
    assert answer("Expiry?",HITS,model="llama3.1:8b")["mode"]=="unverified"


def test_llm_not_called_without_evidence(monkeypatch):
    post=Mock()
    monkeypatch.setattr("folio.answering.httpx.post",post)
    assert answer("Expiry?",[],model="llama3.1:8b")["mode"]=="abstained"
    post.assert_not_called()


def test_paddle_v3_result_schema(monkeypatch):
    engine=Mock()
    engine.predict.return_value=[{"rec_texts":["Passport","Expiry: 2032-06-10"]}]
    factory=Mock(return_value=engine)
    monkeypatch.setitem(sys.modules,"paddleocr",types.SimpleNamespace(PaddleOCR=factory))
    extractor=Extractor("paddle")
    assert extractor.ocr(Image.new("RGB",(200,100)))=="Passport\nExpiry: 2032-06-10"
    factory.assert_called_once()


def test_metadata_does_not_confuse_parent_with_holder():
    text="PAN card\nFather name: Arun\nName: Meera Rao\nPAN number: ABCDE1234F"
    entities=EntityExtractor().extract(text)
    assert [e["text"] for e in entities if e["label"]=="name"]==["Meera Rao"]


def test_original_file_lifecycle(tmp_path):
    from folio.service import Assistant
    service=Assistant(Settings(data_dir=tmp_path))
    content=b"Passport number: P1234567\nName: Sam\nExpiry date: 2032-06-10"
    d=service.ingest(content,"../../outside.txt")
    assert d["filename"]=="outside.txt"
    assert service.store.original(d["id"])==content
    service.store.delete(d["id"])
    assert service.store.original(d["id"]) is None


def test_retrieval_uses_current_library():
    retriever=Retriever()
    doc={"id":"1","filename":"passport.txt","pages":[{"page":1,"text":"Passport expiry 2032"}]}
    assert retriever.search("passport",[doc])
    assert not retriever.search("passport",[])
