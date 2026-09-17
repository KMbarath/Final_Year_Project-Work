import hashlib
import hmac
import re
import secrets
import sqlite3
import time

SESSION_SECONDS=7*86400


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    value=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),600000).hex()
    return salt+":"+value


class Accounts:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS verification_tokens(digest TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_attempts(key TEXT NOT NULL,at REAL NOT NULL);
            """)

    @staticmethod
    def public(row):
        return {"id":row["id"],"email":row["email"],"email_verified":bool(row["verified"])}

    def by_id(self,uid):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        return self.public(row) if row else None

    def by_email(self,email):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
        return self.public(row) if row else None

    def signup(self,email,password):
        email=email.strip().lower()
        if len(email)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",email):
            raise ValueError("Enter a valid email address.")
        if not 10<=len(password)<=128:
            raise ValueError("Password must contain 10 to 128 characters.")
        uid=secrets.token_hex(16)
        hashed=password_hash(password)
        try:
            with self.store.connect() as db:
                db.execute("INSERT INTO users VALUES (?,?,?,0,?)",(uid,email,hashed,time.time()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with this email already exists. Please log in.") from exc
        return self.by_id(uid)

    def rate_limit(self,key,limit=8,window=300):
        now=time.time()
        with self.store.connect() as db:
            db.execute("DELETE FROM auth_attempts WHERE at<?",(now-window,))
            count=db.execute("SELECT COUNT(*) FROM auth_attempts WHERE key=?",(key,)).fetchone()[0]
            if count>=limit:return False
            db.execute("INSERT INTO auth_attempts VALUES (?,?)",(key,now))
        return True

    def login(self,email,password):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
        saved=row["password"] if row else "0"*32+":"+"0"*64
        computed=password_hash(password,saved.split(":")[0])
        return self.public(row) if row and hmac.compare_digest(saved,computed) else None

    def session(self,uid):
        token=secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?",(time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)",(token_hash(token),uid,time.time()+SESSION_SECONDS))
        return token

    def authenticate(self,token):
        if not token or len(token)>128:return None
        with self.store.connect() as db:
            row=db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=? AND s.expires>?",(token_hash(token),time.time())).fetchone()
        return self.public(row) if row else None

    def logout(self,token):
        with self.store.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest=?",(token_hash(token or ""),))

    def verification(self,uid):
        token=secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute("DELETE FROM verification_tokens WHERE user_id=?",(uid,))
            db.execute("INSERT INTO verification_tokens VALUES (?,?,?)",(token_hash(token),uid,time.time()+86400))
        return token

    def verify(self,token):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM verification_tokens WHERE digest=? AND expires>?",(token_hash(token),time.time())).fetchone()
            if row is None:return False
            db.execute("UPDATE users SET verified=1 WHERE id=?",(row["user_id"],))
            db.execute("DELETE FROM verification_tokens WHERE user_id=?",(row["user_id"],))
        return True
