import json
import sqlite3
from folio.storage import Store


def test_old_local_library_is_preserved_and_not_exposed_to_accounts(tmp_path):
    path=tmp_path/"folio.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE documents(id TEXT PRIMARY KEY,filename TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,pages TEXT NOT NULL,classification TEXT NOT NULL,entities TEXT NOT NULL,
            expiry_date TEXT,expiry_confirmed INTEGER DEFAULT 0)""")
        db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)",("legacy","existing.pdf","hash","2026-01-01",
            json.dumps([{"page":1,"text":"Original private text"}]),json.dumps({"label":"unknown"}),"[]",None,0))
    store=Store(tmp_path)
    assert store.get("legacy")["filename"]=="existing.pdf"
    assert store.list("new-account")==[]
    assert store.get("legacy","new-account") is None
    assert (tmp_path/"folio.before-accounts.sqlite3").exists()
    Store(tmp_path) # Idempotent migration; does not reassign documents.
    assert len(store.list())==1
