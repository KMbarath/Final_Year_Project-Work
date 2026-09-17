import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date,datetime,timezone


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
              document_type TEXT DEFAULT 'unknown');
            CREATE TABLE IF NOT EXISTS originals(
              document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,content BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS notifications(
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              expiry_date TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,
              PRIMARY KEY(document_id,expiry_date));
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
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(
              id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,title TEXT NOT NULL,
              document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
              id INTEGER PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
              role TEXT NOT NULL,content TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS docs_owner ON documents(owner_id);
            CREATE INDEX IF NOT EXISTS chats_owner ON conversations(owner_id);
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

    def list(self,owner_id=None):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM documents WHERE owner_id IS ? ORDER BY created_at DESC",(owner_id,))]

    def get(self,document_id,owner_id=None):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM documents WHERE id=? AND owner_id IS ?",(document_id,owner_id)).fetchone())

    def by_digest(self,digest,owner_id=None):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM documents WHERE digest=? AND owner_id IS ?",(digest,owner_id)).fetchone())

    def add(self,item):
        with self.connect() as db:
            db.execute("INSERT INTO documents(id,filename,digest,created_at,pages,classification,entities,expiry_date,owner_id,document_type) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item["id"],item["filename"],item["digest"],now(),json.dumps(item["pages"]),json.dumps(item["classification"]),
                 json.dumps(item["entities"]),item["expiry_date"],item.get("owner_id"),item.get("document_type", "unknown")))
            if item.get("content") is not None:
                db.execute("INSERT INTO originals VALUES (?,?)",(item["id"],item["content"]))
        return self.get(item["id"],item.get("owner_id"))

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
            row=db.execute("SELECT o.content FROM originals o JOIN documents d ON d.id=o.document_id WHERE d.id=? AND d.owner_id IS ?",(document_id,owner_id)).fetchone()
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
