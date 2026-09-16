from datetime import date
from email.message import EmailMessage
from email.utils import make_msgid
import smtplib
import ssl
import threading
import time


class Mailer:
    def __init__(self,settings):self.settings=settings

    @property
    def configured(self):
        return bool(self.settings.smtp_host and self.settings.smtp_from)

    def send(self,recipient,subject,body,message_id=None):
        if not self.configured:raise RuntimeError("SMTP is not configured.")
        message=EmailMessage()
        message["From"]=self.settings.smtp_from
        message["To"]=recipient
        message["Subject"]=subject
        message["Message-ID"]=message_id or make_msgid(domain="folio.local")
        message.set_content(body)
        s=self.settings
        factory=smtplib.SMTP_SSL if s.smtp_security=="ssl" else smtplib.SMTP
        kwargs={"host":s.smtp_host,"port":s.smtp_port,"timeout":20}
        if s.smtp_security=="ssl":kwargs["context"]=ssl.create_default_context()
        with factory(**kwargs) as smtp:
            if s.smtp_security=="starttls":smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username:smtp.login(s.smtp_username,s.smtp_password)
            smtp.send_message(message)


class Notifications:
    def __init__(self,store,mailer):
        self.store,self.mailer=store,mailer
        self.lock=threading.Lock()
        with store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS email_outbox(
                id INTEGER PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                expiry_date TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,
                sent_at REAL,last_error TEXT,UNIQUE(document_id,expiry_date,kind));
            """)

    def queue(self,today=None):
        today=today or date.today()
        self.store.refresh_reminders(today)
        with self.store.connect() as db:
            rows=db.execute("SELECT * FROM documents WHERE owner_id IS NOT NULL AND expiry_date IS NOT NULL").fetchall()
            for row in rows:
                days=(date.fromisoformat(row["expiry_date"])-today).days
                if days>30:continue
                kind="expired" if days<=0 else "upcoming"
                if kind=="expired":
                    db.execute("DELETE FROM email_outbox WHERE document_id=? AND kind='upcoming' AND status!='sent'",(row["id"],))
                db.execute("INSERT OR IGNORE INTO email_outbox(user_id,document_id,expiry_date,kind) VALUES (?,?,?,?)",(row["owner_id"],row["id"],row["expiry_date"],kind))

    def tick(self,today=None):
        with self.lock:
            self.queue(today)
            if not self.mailer.configured:return
            with self.store.connect() as db:
                rows=db.execute("""SELECT e.*,u.email,d.filename FROM email_outbox e
                    JOIN users u ON u.id=e.user_id JOIN documents d ON d.id=e.document_id
                    WHERE e.status IN ('pending','failed') AND e.next_attempt<=? AND u.verified=1
                    AND d.expiry_date=e.expiry_date ORDER BY e.id LIMIT 25""",(time.time(),)).fetchall()
            for row in rows:
                try:
                    stage="has reached its expiry date" if row["kind"]=="expired" else "expires within 30 days"
                    self.mailer.send(row["email"],"Folio document expiry reminder",
                        f"Your document {row['filename']} {stage}.\nExpiry date: {row['expiry_date']}\n\nOpen Folio to review it. Automatically extracted dates should be checked against the original.",
                        f"<expiry-{row['id']}@folio.local>")
                except Exception as exc:
                    attempts=row["attempts"]+1
                    delay=min(86400,60*2**min(attempts,10))
                    with self.store.connect() as db:
                        db.execute("UPDATE email_outbox SET status='failed',attempts=?,next_attempt=?,last_error=? WHERE id=?",(attempts,time.time()+delay,type(exc).__name__,row["id"]))
                else:
                    with self.store.connect() as db:
                        db.execute("UPDATE email_outbox SET status='sent',attempts=attempts+1,sent_at=?,last_error=NULL WHERE id=?",(time.time(),row["id"]))
