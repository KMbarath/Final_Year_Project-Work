"""Assign pre-account documents to a specified account, from a trusted local terminal."""
import argparse
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from folio.config import Settings
from folio.storage import Store
from folio.accounts import Accounts


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--email",required=True,help="An existing account that should own the old local library.")
    args=p.parse_args()
    settings=Settings();settings.prepare()
    store=Store(settings.data_dir);Accounts(store)
    with store.connect() as db:
        user=db.execute("SELECT id FROM users WHERE email=?",(args.email.strip().lower(),)).fetchone()
        if not user:raise SystemExit("Create the account in Folio first.")
        rows=db.execute("SELECT d.id,d.digest,o.content FROM documents d LEFT JOIN originals o ON o.document_id=d.id WHERE d.owner_id IS NULL").fetchall()
        for row in rows:
            digest=hashlib.sha256(user["id"].encode()+(row["content"] or row["digest"].encode())).hexdigest()
            if db.execute("SELECT id FROM documents WHERE digest=?",(digest,)).fetchone():
                # Preserve the original instead of deleting a possible duplicate.
                digest=hashlib.sha256((digest+row["id"]).encode()).hexdigest()
            db.execute("UPDATE documents SET owner_id=?,digest=? WHERE id=?",(user["id"],digest,row["id"]))
    print("Assigned",len(rows),"legacy document(s) to the selected account.")


if __name__=="__main__":main()
