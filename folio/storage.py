import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date,datetime,timezone
from .categories import categorize


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self,folder):
        folder.mkdir(parents=True,exist_ok=True)
        self.path=folder/"folio.sqlite3"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,filename TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,pages TEXT NOT NULL,classification TEXT NOT NULL,
              entities TEXT NOT NULL,expiry_date TEXT,expiry_confirmed INTEGER DEFAULT 0,owner_id TEXT,
              document_type TEXT DEFAULT 'unknown',vault_category TEXT DEFAULT 'other');
            CREATE TABLE IF NOT EXISTS originals(
              document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,content BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS notifications(
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              expiry_date TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,
              PRIMARY KEY(document_id,expiry_date));
                        CREATE TABLE IF NOT EXISTS document_shares(
                            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                            user_id TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            PRIMARY KEY(document_id,user_id));
            """)
            columns={r["name"] for r in db.execute("PRAGMA table_info(documents)")}
            if "owner_id" not in columns:
                backup=folder/"folio.before-accounts.sqlite3"
                if not backup.exists():
                    with sqlite3.connect(backup) as target:
                        db.backup(target)
                db.execute("ALTER TABLE documents ADD COLUMN owner_id TEXT")
            if "document_type" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN document_type TEXT DEFAULT 'unknown'")
            if "vault_category" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN vault_category TEXT DEFAULT 'other'")
            # Existing local uploads predate vault folders. Classify them once from
            # their saved extracted text so they appear in the right folder too.
            for row in db.execute("SELECT id,pages,classification,document_type,vault_category FROM documents WHERE vault_category IS NULL OR vault_category='other'"):
                pages=json.loads(row["pages"])
                classification=json.loads(row["classification"])
                category=categorize("\n".join(page.get("text","") for page in pages),row["document_type"] or "",classification.get("label", ""))
                if category != (row["vault_category"] or "other"):
                    db.execute("UPDATE documents SET vault_category=? WHERE id=?",(category,row["id"]))
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(
              id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,title TEXT NOT NULL,
              document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
              id INTEGER PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
              role TEXT NOT NULL,content TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_events(
              id INTEGER PRIMARY KEY,owner_id TEXT NOT NULL,event TEXT NOT NULL,
              document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
              detail TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS docs_owner ON documents(owner_id);
            CREATE INDEX IF NOT EXISTS chats_owner ON conversations(owner_id);
            CREATE INDEX IF NOT EXISTS audit_owner_created ON audit_events(owner_id,created_at DESC);
            """)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:yield db
        finally:db.close()

    @staticmethod
    def decode(row):
        if row is None:return None
        item=dict(row)
        for field in ("pages","classification","entities"):item[field]=json.loads(item[field])
        item["expiry_confirmed"]=bool(item["expiry_confirmed"])
        return item

    def list(self,owner_id=None,category=None):
        with self.connect() as db:
            query="""SELECT d.* FROM documents d
                WHERE (d.owner_id IS ? OR EXISTS (SELECT 1 FROM document_shares s WHERE s.document_id=d.id AND s.user_id=?))"""
            values=[owner_id,owner_id]
            if category:
                query+=" AND d.vault_category=?"; values.append(category)
            query+=" ORDER BY d.created_at DESC"
            return [self.decode(r) for r in db.execute(query,values)]

    def get(self,document_id,owner_id=None):
        with self.connect() as db:
            return self.decode(db.execute("""SELECT d.* FROM documents d
                WHERE d.id=? AND (d.owner_id IS ? OR EXISTS (SELECT 1 FROM document_shares s WHERE s.document_id=d.id AND s.user_id=?))""",
                (document_id,owner_id,owner_id)).fetchone())

    def share(self,document_id,user_id,owner_id):
        with self.connect() as db:
            owner=db.execute("SELECT 1 FROM documents WHERE id=? AND owner_id=?",(document_id,owner_id)).fetchone()
            if owner is None:return False
            db.execute("INSERT OR IGNORE INTO document_shares VALUES (?,?,?)",(document_id,user_id,now()))
        return True

    def unshare(self,document_id,user_id,owner_id):
        with self.connect() as db:
            owner=db.execute("SELECT 1 FROM documents WHERE id=? AND owner_id=?",(document_id,owner_id)).fetchone()
            if owner is None:return False
            db.execute("DELETE FROM document_shares WHERE document_id=? AND user_id=?",(document_id,user_id))
        return True

    def shares(self,document_id,owner_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT s.user_id,s.created_at,u.email
                FROM document_shares s JOIN users u ON u.id=s.user_id
                JOIN documents d ON d.id=s.document_id WHERE s.document_id=? AND d.owner_id=?""",
                (document_id,owner_id))]

    def by_digest(self,digest,owner_id=None):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM documents WHERE digest=? AND owner_id IS ?",(digest,owner_id)).fetchone())

    def add(self,item):
        with self.connect() as db:
            db.execute("INSERT INTO documents(id,filename,digest,created_at,pages,classification,entities,expiry_date,owner_id,document_type,vault_category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (item["id"],item["filename"],item["digest"],now(),json.dumps(item["pages"]),json.dumps(item["classification"]),
                 json.dumps(item["entities"]),item["expiry_date"],item.get("owner_id"),item.get("document_type", "unknown"),item.get("vault_category", "other")))
            if item.get("content") is not None:
                db.execute("INSERT INTO originals VALUES (?,?)",(item["id"],item["content"]))
        return self.get(item["id"],item.get("owner_id"))

    def replace_analysis(self,document_id,item,owner_id=None):
        """Replace derived OCR data while retaining the original upload and user choices."""
        with self.connect() as db:
            found=db.execute("SELECT id FROM documents WHERE id=? AND owner_id IS ?",(document_id,owner_id)).fetchone()
            if found is None:return None
            db.execute("""UPDATE documents SET pages=?,classification=?,entities=?,
                        expiry_date=CASE WHEN expiry_confirmed=1 THEN expiry_date ELSE ? END,
                        document_type=?,vault_category=? WHERE id=?""",
                       (json.dumps(item["pages"]),json.dumps(item["classification"]),json.dumps(item["entities"]),
                        item["expiry_date"],item.get("document_type","unknown"),item.get("vault_category","other"),document_id))
        return self.get(document_id,owner_id)

    def confirm_expiry(self,document_id,value,owner_id=None):
        if value:value=date.fromisoformat(value).isoformat()
        with self.connect() as db:
            found=db.execute("SELECT expiry_date FROM documents WHERE id=? AND owner_id IS ?",(document_id,owner_id)).fetchone()
            if found is None:return None
            db.execute("UPDATE documents SET expiry_date=?,expiry_confirmed=1 WHERE id=?",(value,document_id))
            if found["expiry_date"] != value:
                db.execute("DELETE FROM notifications WHERE document_id=?",(document_id,))
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='email_outbox'").fetchone():
                    db.execute("DELETE FROM email_outbox WHERE document_id=?",(document_id,))
        return self.get(document_id,owner_id)

    def delete(self,document_id,owner_id=None):
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE id=? AND owner_id IS ?",(document_id,owner_id))

    def refresh_reminders(self,today=None):
        today=today or date.today()
        with self.connect() as db:
            rows=db.execute("SELECT * FROM documents WHERE expiry_date IS NOT NULL").fetchall()
            for row in rows:
                days=(date.fromisoformat(row["expiry_date"])-today).days
                if days<=30:
                    state="expires today" if days==0 else (f"expired {-days} days ago" if days<0 else f"expires in {days} days")
                    db.execute("INSERT INTO notifications VALUES (?,?,?,?) ON CONFLICT(document_id,expiry_date) DO UPDATE SET message=excluded.message",
                               (row["id"],row["expiry_date"],f"{row['filename']} {state}.",now()))
                else:
                    db.execute("DELETE FROM notifications WHERE document_id=?",(row["id"],))

    def reminders(self,today=None,owner_id=None):
        self.refresh_reminders(today)
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT n.*,d.expiry_confirmed FROM notifications n JOIN documents d ON d.id=n.document_id
                WHERE d.owner_id IS ? ORDER BY n.expiry_date""",(owner_id,))]

    def original(self,document_id,owner_id=None):
        with self.connect() as db:
            row=db.execute("""SELECT o.content FROM originals o JOIN documents d ON d.id=o.document_id
                WHERE d.id=? AND (d.owner_id IS ? OR EXISTS (SELECT 1 FROM document_shares s WHERE s.document_id=d.id AND s.user_id=?))""",
                (document_id,owner_id,owner_id)).fetchone()
        return row["content"] if row else None

    def new_chat(self,owner_id,document_id=None):
        if document_id and not self.get(document_id,owner_id):
            raise ValueError("Selected document no longer exists.")
        cid=uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?)",(cid,owner_id,"New chat",document_id,now(),now()))
        return self.chat(cid,owner_id)

    def chats(self,owner_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM conversations WHERE owner_id=? ORDER BY updated_at DESC",(owner_id,))]

    def chat(self,cid,owner_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM conversations WHERE id=? AND owner_id=?",(cid,owner_id)).fetchone()
            if row is None:return None
            item=dict(row)
            item["messages"]=[{**dict(r),"payload":json.loads(r["payload"])} for r in db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY id",(cid,))]
        return item

    def append_turn(self,cid,owner_id,question,result,document_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM conversations WHERE id=? AND owner_id=?",(cid,owner_id)).fetchone()
            if row is None:raise ValueError("Conversation not found.")
            for role,content,payload in [("user",question,{}),("assistant",result["answer"],result)]:
                db.execute("INSERT INTO messages(conversation_id,role,content,payload,created_at) VALUES (?,?,?,?,?)",
                           (cid,role,content,json.dumps(payload),now()))
            title=question[:70] if row["title"]=="New chat" else row["title"]
            db.execute("UPDATE conversations SET title=?,document_id=?,updated_at=? WHERE id=?",(title,document_id,now(),cid))

    def delete_chat(self,cid,owner_id):
        with self.connect() as db:
            db.execute("DELETE FROM conversations WHERE id=? AND owner_id=?",(cid,owner_id))

    def audit(self,owner_id,event,document_id=None,detail=""):
        """Record a concise private event without keeping document text or credentials."""
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(owner_id,event,document_id,detail,created_at) VALUES (?,?,?,?,?)",
                       (owner_id,event,document_id,detail[:200],now()))

    def dashboard(self,owner_id,today=None):
        today=today or date.today()
        documents=self.list(owner_id)
        total_bytes=sum(len(self.original(d["id"],owner_id) or b"") for d in documents)
        recommendations=[]
        for document in documents:
            if not document["expiry_date"]:
                continue
            days=(date.fromisoformat(document["expiry_date"])-today).days
            if days < 0:
                message=f"Review {document['filename']}: it expired {-days} day(s) ago."
            elif days == 0:
                message=f"Renew or review {document['filename']}: it expires today."
            elif days <= 60:
                message=f"Plan renewal for {document['filename']}: it expires in {days} day(s)."
            else:
                continue
            recommendations.append({"document_id":document["id"],"message":message})
        with self.connect() as db:
            activity=[dict(row) for row in db.execute("SELECT event,document_id,detail,created_at FROM audit_events WHERE owner_id=? ORDER BY id DESC LIMIT 8",(owner_id,))]
        return {"document_count":len(documents),"storage_bytes":total_bytes,
                "upcoming_expiries":sum(bool(d["expiry_date"]) and (date.fromisoformat(d["expiry_date"])-today).days<=30 for d in documents),
                "recommendations":recommendations[:5],"recent_activity":activity}
