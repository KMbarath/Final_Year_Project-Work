import asyncio
import importlib.util
import json
import logging
import shutil
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import date
from fastapi import FastAPI,File,UploadFile,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,Response,RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from starlette.concurrency import run_in_threadpool
from .config import Settings,ROOT
from .service import Assistant
from .extraction import FeatureUnavailable
from .accounts import Accounts,SESSION_SECONDS
from .mail import Mailer,Notifications

log=logging.getLogger(__name__)
COOKIE="folio_session"


class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=1,max_length=128)


class Question(BaseModel):
    question:str=Field(min_length=2,max_length=2000)
    document_id:str|None=None
    conversation_id:str|None=None
    language:str="en"


class ChatCreate(BaseModel):
    document_id:str|None=None


class Speech(BaseModel):
    text:str=Field(min_length=1,max_length=4000)


class Expiry(BaseModel):
    expiry_date:date|None=None


def create_app(settings=None):
    settings=settings or Settings()
    assistant=Assistant(settings)
    accounts=Accounts(assistant.store)
    mailer=Mailer(settings)
    notifications=Notifications(assistant.store,mailer)

    async def reminder_loop():
        while True:
            try:await run_in_threadpool(notifications.tick)
            except Exception:log.exception("Reminder check failed")
            await asyncio.sleep(60)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(reminder_loop())
        yield
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

    app=FastAPI(title="Folio Document Assistant",version="0.2.0",lifespan=lifespan)
    app.state.assistant=assistant
    app.state.accounts=accounts
    app.state.notifications=notifications
    app.state.mailer=mailer

    @app.middleware("http")
    async def security(request:Request,call_next):
        origin=request.headers.get("origin")
        allowed_origins={str(request.base_url).rstrip("/"),settings.public_url.rstrip("/")}
        if origin and origin not in allowed_origins:
            return JSONResponse({"detail":"Cross-origin requests are disabled."},status_code=403)
        if request.url.hostname not in settings.allowed_hosts and "*" not in settings.allowed_hosts:
            return JSONResponse({"detail":"Host is not allowed."},status_code=403)
        request.state.user=accounts.authenticate(request.cookies.get(COOKIE))
        public={"/api/status","/api/auth/signup","/api/auth/login","/api/auth/verify"}
        if request.url.path.startswith("/api/") and request.url.path not in public and not request.state.user:
            return JSONResponse({"detail":"Please log in to continue."},status_code=401)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Cache-Control"]="no-store"
        response.headers["Content-Security-Policy"]="default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(FeatureUnavailable)
    async def unavailable(request,exc):return JSONResponse({"detail":str(exc)},status_code=503)

    @app.exception_handler(ValueError)
    async def invalid(request,exc):return JSONResponse({"detail":str(exc)},status_code=400)

    @app.exception_handler(Exception)
    async def failure(request,exc):
        log.exception("Request failed")
        return JSONResponse({"detail":"Processing failed. Check the server log and model setup."},status_code=500)

    def uid(request):return request.state.user["id"]

    def throttle(request,name,limit=8):
        key=name+":"+(request.client.host if request.client else "local")
        if not accounts.rate_limit(key,limit=limit):raise HTTPException(429,"Too many attempts. Try again in five minutes.")

    def set_session(response,user):
        response.set_cookie(COOKIE,accounts.session(user["id"]),max_age=SESSION_SECONDS,httponly=True,
                            secure=settings.secure_cookies,samesite="strict",path="/")

    def send_verification(user):
        if not mailer.configured:return "not_configured"
        token=accounts.verification(user["id"])
        link=settings.public_url.rstrip("/")+"/api/auth/verify?token="+quote(token)
        try:mailer.send(user["email"],"Verify your Folio email",f"Confirm your email to receive document expiry reminders.\n\n{link}\n\nThis link expires in 24 hours. If you did not create an account, ignore this message.")
        except Exception:return "failed"
        return "sent"

    @app.post("/api/auth/signup",status_code=201)
    def signup(body:Credentials,request:Request,response:Response):
        throttle(request,"signup",5)
        user=accounts.signup(body.email,body.password)
        set_session(response,user)
        return {"user":user,"verification_email":send_verification(user)}

    @app.post("/api/auth/login")
    def login(body:Credentials,request:Request,response:Response):
        throttle(request,"login")
        user=accounts.login(body.email,body.password)
        if user is None:raise HTTPException(401,"Email or password is incorrect.")
        set_session(response,user)
        return {"user":user}

    @app.post("/api/auth/logout")
    def logout(request:Request,response:Response):
        accounts.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE,path="/")
        return {"ok":True}

    @app.get("/api/auth/me")
    def me(request:Request):
        return {"user":request.state.user,"email_configured":mailer.configured}

    @app.post("/api/auth/resend-verification")
    def resend(request:Request):
        throttle(request,"verify",3)
        if request.state.user["email_verified"]:return {"verification_email":"already_verified"}
        return {"verification_email":send_verification(request.state.user)}

    @app.get("/api/auth/verify")
    def verify(token:str):
        if len(token)>128 or not accounts.verify(token):raise HTTPException(400,"Verification link is invalid or expired.")
        return RedirectResponse("/?email_verified=1",status_code=303)

    @app.get("/api/status")
    def status():
        return {"mode":"local accounts","authentication":True,"classifier":settings.classifier_backend,
            "classifier_ready":settings.classifier_path.exists(),
            "retrieval":"BGE/FAISS + BM25" if settings.embedding_model else "BM25",
            "embedding_model":settings.embedding_model or None,"answers":settings.ollama_model or "source excerpts",
            "structured_extraction":settings.extraction_model or "prompt schema + labelled fallback",
            "prompt_document_types":len(assistant.prompt_extractor.catalog.specs),
            "extraction_model_error":assistant.prompt_extractor.last_error or None,
            "ocr":settings.ocr_backend,"ocr_installed":bool(shutil.which("tesseract")) if settings.ocr_backend=="tesseract" else bool(importlib.util.find_spec("paddleocr")),
            "entities":settings.entity_model or "labelled fields","whisper_installed":bool(importlib.util.find_spec("whisper")),
            "piper_configured":bool(settings.piper_model),"translation_configured":bool(settings.translation_model),
            "email_configured":mailer.configured}

    def owned(document_id,request):
        found=assistant.store.get(document_id,uid(request))
        if found is None:raise HTTPException(404,"Document not found.")
        return found

    @app.get("/api/documents")
    def documents(request:Request):return assistant.store.list(uid(request))

    @app.post("/api/documents",status_code=201)
    async def upload(request:Request,file:UploadFile=File(...)):
        data=await file.read(settings.max_upload_bytes+1)
        await file.close()
        if len(data)>settings.max_upload_bytes:raise HTTPException(413,"Maximum upload size is 20 MB.")
        result=await run_in_threadpool(assistant.ingest,data,file.filename or "document.txt",uid(request))
        await run_in_threadpool(notifications.queue)
        return result

    @app.get("/api/documents/{document_id}")
    def document(document_id:str,request:Request):return owned(document_id,request)

    @app.get("/api/documents/{document_id}/download")
    def download(document_id:str,request:Request):
        found=owned(document_id,request)
        original=assistant.store.original(document_id,uid(request))
        if original is None:raise HTTPException(404,"Original document not found.")
        return Response(original,media_type="application/octet-stream",
                        headers={"Content-Disposition":"attachment; filename*=UTF-8''"+quote(found["filename"])})

    @app.delete("/api/documents/{document_id}",status_code=204)
    def delete(document_id:str,request:Request):
        with assistant.lock:
            owned(document_id,request)
            assistant.store.delete(document_id,uid(request))
            assistant.retriever._cache_key=None
        return Response(status_code=204)

    @app.patch("/api/documents/{document_id}/expiry")
    def expiry(document_id:str,body:Expiry,request:Request):
        owned(document_id,request)
        result=assistant.store.confirm_expiry(document_id,body.expiry_date.isoformat() if body.expiry_date else None,uid(request))
        notifications.queue()
        return result

    @app.get("/api/conversations")
    def chats(request:Request):return assistant.store.chats(uid(request))

    @app.post("/api/conversations",status_code=201)
    def new_chat(body:ChatCreate,request:Request):return assistant.store.new_chat(uid(request),body.document_id)

    @app.get("/api/conversations/{cid}")
    def chat_detail(cid:str,request:Request):
        result=assistant.store.chat(cid,uid(request))
        if result is None:raise HTTPException(404,"Conversation not found.")
        return result

    @app.delete("/api/conversations/{cid}",status_code=204)
    def delete_chat(cid:str,request:Request):
        if assistant.store.chat(cid,uid(request)) is None:raise HTTPException(404,"Conversation not found.")
        assistant.store.delete_chat(cid,uid(request))
        return Response(status_code=204)

    @app.post("/api/chat")
    def chat(body:Question,request:Request):
        if not body.question.strip():raise HTTPException(400,"Enter a question.")
        with assistant.lock:
            if body.conversation_id:
                conversation=assistant.store.chat(body.conversation_id,uid(request))
                if conversation is None:raise HTTPException(404,"Conversation not found.")
            else:
                conversation=assistant.store.new_chat(uid(request),body.document_id)
            scope=body.document_id or conversation["document_id"]
            if scope:owned(scope,request)
            result=assistant.ask(body.question.strip(),scope,body.language,uid(request),conversation["messages"])
            result["conversation_id"]=conversation["id"]
            assistant.store.append_turn(conversation["id"],uid(request),body.question.strip(),result,scope)
            return result

    @app.get("/api/reminders")
    def reminders(request:Request):
        notifications.queue()
        results=assistant.store.reminders(owner_id=uid(request))
        with assistant.store.connect() as db:
            emails=[dict(r) for r in db.execute("SELECT document_id,kind,status FROM email_outbox WHERE user_id=?",(uid(request),))]
        for row in results:
            row["email_delivery"]=[r for r in emails if r["document_id"]==row["document_id"]]
        return results

    @app.post("/api/transcribe")
    async def transcribe(request:Request,file:UploadFile=File(...)):
        suffix=Path(file.filename or "").suffix.lower()
        if suffix not in {".wav",".webm",".mp3",".m4a",".ogg"}:raise HTTPException(400,"Unsupported audio format.")
        content=await file.read(settings.max_upload_bytes+1)
        await file.close()
        if not content or len(content)>settings.max_upload_bytes:raise HTTPException(413,"Audio must be nonempty and below 20 MB.")
        return {"text":await run_in_threadpool(assistant.transcribe,content,suffix)}

    @app.post("/api/speak")
    def speak(body:Speech):
        with assistant.lock:return Response(assistant.voice.synthesize(body.text),media_type="audio/wav")

    @app.get("/api/training")
    def training():
        result={}
        for name in ["baseline","minilm","evaluation","optional"]:
            path=ROOT/"artifacts"/name/"report.json"
            if path.exists():result[name]=json.loads(path.read_text())
        return result

    static=Path(__file__).parent/"static"
    app.mount("/static",StaticFiles(directory=static),name="static")

    @app.get("/")
    def home():return FileResponse(static/"index.html")
    return app


app=create_app()
