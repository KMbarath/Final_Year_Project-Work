# Folio — personal document assistant

A local document assistant with account-separated workspaces based on the supplied architecture PDF.
Upload PDF scans, images or text; inspect extracted details; ask questions with page references;
use voice adapters and optional translation; receive in-app expiry reminders.

**Accuracy status:** no real labelled dataset was supplied. Both a TF-IDF classifier and
MiniLM were actually trained on 1,152 synthetic examples. Their held-out synthetic accuracy
is 100%; this is not a claim of 100% accuracy on real documents. See the saved reports and
[executed notebook](notebooks/model_training.executed.ipynb).

## Start on this computer

From PowerShell in this folder:

~~~powershell
.\scripts\start.ps1 -Background
~~~

Open http://127.0.0.1:8000 and create an account or log in. Use the sample PDF, scanned PDF, PNG or TXT files in
[data/samples](data/samples). Add a document, inspect its extracted fields, confirm its
expiry date if needed, and ask a question. Each account has a private library and saved conversations. Pre-account documents are preserved but need explicit local assignment; see [accounts and notifications](docs/ACCOUNTS_AND_NOTIFICATIONS.md).

Use the trained MiniLM classifier:

~~~powershell
.\scripts\start.ps1 -Transformer
~~~

The launch script automatically enables the downloaded BGE-small search model and Piper voice when their local files exist. Whisper-base is cached locally. BGE-M3 remains a configurable larger alternative.

The server binds to localhost. Keep one worker: heavyweight models are loaded once and
accessed serially. Stop with Ctrl+C. The local database is in data/private/folio.sqlite3.

## Install on another computer

Python 3.10 or 3.11 is recommended.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[training,dev]"
.\.venv\Scripts\python.exe -m training.baseline --generate-demo
.\.venv\Scripts\python.exe -m training.evaluate
.\scripts\start.ps1
~~~

Install Tesseract and put it on PATH for image/scanned-PDF OCR. Native PDFs and text
work without OCR. For CUDA training, install a PyTorch build matching your system.
On this computer, the project environment reuses the existing CUDA-enabled PyTorch.

## Training and notebooks

Open [notebooks/model_training.ipynb](notebooks/model_training.ipynb) in VS Code or Jupyter.
Select the project Python interpreter. The executed copy includes charts and measured outputs.

~~~powershell
.\.venv\Scripts\python.exe -m jupyterlab notebooks/model_training.ipynb
.\scripts\train.ps1 -Transformer
~~~

The pipeline performs:
1. Provenance audit, normalized exact deduplication, and disjoint group splits.
2. Clean baseline training, then OCR-augmented training with regularization candidates.
3. Validation-loss checkpoint selection and early stopping, never selection on test scores.
4. MiniLM classification-head warmup, then encoder fine-tuning at a smaller learning rate.
5. Held-out classification metrics and independent OCR/entity/retrieval fixture evaluation.

MiniLM uses dropout, weight decay, label smoothing, class weights and gradient clipping.
Fit diagnostics flag possible overfitting/underfitting; they cannot guarantee either is absent.
Epoch histories, split manifests, model checkpoints and evaluation reports live in artifacts/.

The notebook defaults to reading the saved MiniLM run. Set RUN_TRANSFORMER_TRAINING=True
to retrain it. Baseline cells really train. Avoid tuning repeatedly against the same test set.

Real-data CSV columns: text,label,group,data_kind. Use data_kind=real and at least six
independent groups per class. Group related people, document sources and duplicate scans
together; inspect near-duplicates. Example command:

~~~powershell
.\.venv\Scripts\python.exe -m training.transformer --dataset data/private/labelled.csv --output artifacts/real_minilm
~~~

## Model integrations

### Prompt-driven extraction

The checked-in `prompts.yaml` catalog is now the source of truth for structured extraction
across 84 document types. Folio identifies the closest catalog type, applies its strict JSON
schema through Ollama, stores the extracted fields with confidence metadata, and adds those
facts to the retrieval index alongside page-preserving OCR text. Set an external Ollama-compatible
endpoint and models with:

~~~bash
FOLIO_OLLAMA_URL=https://your-ollama-host.example
FOLIO_EXTRACTION_MODEL=qwen2.5:7b
FOLIO_OLLAMA_MODEL=qwen2.5:7b
~~~

If the model endpoint is unavailable, labelled fields are still extracted against the selected
prompt schema and the failure is reported by `/api/status`. This fallback is deliberately
conservative; production-quality extraction still depends on a capable vision/OCR pipeline,
model, and representative evaluation documents.

The lightweight profile is usable without downloading every model. It clearly reports its
active backends in Model lab and GET /api/status. Heavy integrations are lazy-loaded; first
use can require network access to download public model weights. Document text is processed
locally; the LLM adapter calls only the configured Ollama-compatible endpoint. For local Ollama,
set `FOLIO_OLLAMA_URL=http://127.0.0.1:11434` explicitly.

| Component | Runnable local profile | Reference architecture integration |
|---|---|---|
| PDF text | PyMuPDF | Native text first; OCR for pages with little text |
| OCR | Tesseract | PaddleOCR 3 via FOLIO_OCR=paddle |
| Classification | Trained character TF-IDF | Trained MiniLM; DistilBERT supported as --model |
| Entities | Labelled-field parsing with source offsets | GLiNER via FOLIO_ENTITY_MODEL |
| Retrieval | BM25 with page-preserving chunks | BGE-M3 + FAISS + BM25 reciprocal-rank fusion |
| Answers | Exact source excerpts | Llama 3.1 / Mistral through an Ollama-compatible endpoint |
| Speech input | Whisper adapter | Microphone capture; editable transcription |
| Speech output | Piper adapter | Local WAV synthesis |
| Translation | English by default | IndicTrans2, ten Indian-language options |
| Reminders | SQLite + lifespan task | Automatic dates; checks every minute; restart catches up |

Enable semantic retrieval:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[semantic]"
$env:FOLIO_EMBEDDING_MODEL="BAAI/bge-m3"
.\scripts\start.ps1
~~~

BGE-M3 uses significant RAM. BAAI/bge-small-en-v1.5 is a smaller English-only option.
Indexes are rebuilt in memory from persisted chunks when documents change. This is
appropriate for a personal library, not a large multi-user service.

Enable PaddleOCR or GLiNER:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr,entities]"
$env:FOLIO_OCR="paddle"
$env:FOLIO_ENTITY_MODEL="urchade/gliner_small-v2.1"
.\scripts\start.ps1
~~~

Install Ollama separately and pull a model:

~~~powershell
ollama pull llama3.1:8b
$env:FOLIO_OLLAMA_MODEL="llama3.1:8b"
.\scripts\start.ps1
~~~

An 8B model will not fit entirely into the RTX 2050's 4 GB VRAM; CPU offloading needs
enough system RAM and will be slower. Generation uses deterministic settings, untrusted
context boundaries and validated source IDs. Source validation does not prove entailment.

Enable voice (the voice extra includes a bundled FFmpeg decoder):

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
.\.venv\Scripts\python.exe -m piper.download_voices --download-dir artifacts/voices en_US-lessac-medium
$env:FOLIO_PIPER_MODEL="$PWD/artifacts/voices/en_US-lessac-medium.onnx"
$env:FOLIO_WHISPER_MODEL="base"
.\scripts\start.ps1
~~~

Piper needs its matching ONNX JSON configuration beside the voice model. The UI limits
recording to 60 seconds. Transcription is editable before asking. English TTS is enabled
only for English answers; other languages need a matching voice.

IndicTrans2 is an optional environment-sensitive integration. Some checkpoints require
accepting the provider's access conditions. Use a compatible Transformers 4.x environment
and follow the official toolkit setup before enabling:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[translation]"
$env:FOLIO_TRANSLATION_MODEL="ai4bharat/indictrans2-en-indic-dist-200M"
.\scripts\start.ps1
~~~

IndicTrans2 requires its published custom model code. Configure only a trusted model
repository. English questions can receive translated answers; cross-language question
translation is not implemented. Long responses may be truncated by the translation model.

## Validation and project layout

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m training.evaluate
.\.venv\Scripts\python.exe scripts/execute_notebook.py
~~~

- folio/: API, storage, extraction, retrieval, models, voice and web interface.
- training/: generated data, baseline, transformer training and pipeline evaluation.
- notebooks/: editable notebook and executed results.
- tests/: functional, data-leakage and regression checks.
- docs/: architecture, evaluation limitations and model provenance.
- scripts/: PowerShell launch/training helpers and browser verification.
- artifacts/: trained weights, histories and reports (excluded from Git).
- data/samples/: clearly fictional upload fixtures.
- data/private/: local personal data (excluded from Git).

## Permanent cloud deployment

The API and mobile-first frontend are one same-origin service, so they deploy together. The
Docker image includes Tesseract and builds the checked-in synthetic baseline classifier during
the image build; private databases and local model caches are never copied into the image.
`render.yaml` describes a no-cost Render service. The free tier sleeps after inactivity and
has an ephemeral filesystem, so uploaded documents and SQLite data can be lost after a restart.
Use a paid persistent disk or an external database/object store for production customer data.

After connecting this repository in Render, set these environment variables before the first deploy:

- `FOLIO_PUBLIC_URL` as the final HTTPS origin, without a trailing slash.
- `FOLIO_ALLOWED_HOSTS` as the deployment hostname.
- `FOLIO_SECURE_COOKIES=1`.
- `FOLIO_REQUIRE_MODELS=0` for the built-in BM25/source-excerpt mode, or set it to `1` only
	after all answer, extraction and embedding model variables are configured.
- `FOLIO_OLLAMA_URL`, `FOLIO_OLLAMA_MODEL`, and `FOLIO_EXTRACTION_MODEL` only when using an
	authenticated external Ollama-compatible service. Keep model credentials in Render secret
	environment variables, never in Git.

Render also supplies `RENDER_EXTERNAL_HOSTNAME`; the application uses it as a fallback for
host validation and verification links when the two public-host variables are not set. Explicit
values are still recommended because they make custom-domain changes deliberate.

Deployment steps:

1. Push this repository to GitHub and confirm the default branch contains `Dockerfile` and `render.yaml`.
2. In Render, choose **New > Blueprint**, connect the repository, and apply `render.yaml`.
3. Set `FOLIO_PUBLIC_URL` to the Render HTTPS URL and `FOLIO_ALLOWED_HOSTS` to its hostname only.
4. Add an SMTP provider's host, port, username, password and sender as Render secret variables if email verification/reminders are required.
5. Deploy and check `https://your-host.example/api/status`; then create an account and upload a sample document.
6. The free plan is suitable for demonstrations only. It may sleep and its ephemeral filesystem
	must not be treated as permanent customer storage.

Do not expose an unauthenticated Ollama server to the internet. Put it behind a private network
or authenticated gateway. The SQLite disk is persistent but not encrypted; use platform disk
encryption and backups for real customer documents.

Original files, extracted text and metadata are stored in the local SQLite database.
It is not encrypted. Password-based accounts and server-side sessions isolate each user's documents and chats. Host/origin checks
restrict the intended localhost use; do not deploy it publicly without a separate
authentication, authorization, encryption and operational review.
Deletion removes the original, text, metadata and reminders; it is not secure disk erasure.

## References

The attached PDF was treated as an architecture reference, not as instructions overriding
the user's request. Its invented classifier checkpoint and older OCR/TTS examples were
replaced with actual APIs and locally trained artifacts.

- [Hugging Face sequence classification](https://github.com/huggingface/transformers/blob/main/docs/source/en/tasks/sequence_classification.md)
- [PaddleOCR Python integration](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [IndicTrans2 model card](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M)

## If chat says it cannot reach the server

Run .\scripts\start.ps1 -Background and refresh the browser. The background process survives closing the launch terminal; logs and its PID are saved under artifacts/server. To stop it, run Stop-Process -Id (Get-Content artifacts/server/server-8000.pid) after checking that the PID still belongs to Folio. Without -Background, leave the launch terminal open. Overview requests show quoted passages from the selected document and do not require the embedding model.

## Accounts, emails and previous conversations

Automatic expiry detection, website reminders, login/signup, per-user chat history and
SMTP email delivery are implemented. See [configuration and test status](docs/ACCOUNTS_AND_NOTIFICATIONS.md).
Gmail delivery still requires a locally entered App Password and email verification.
Use scripts/start-gmail.ps1 to supply credentials without saving them in project files.
