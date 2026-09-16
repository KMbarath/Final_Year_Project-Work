# Build and verification status

## Voice and direct-answer repair (2026-09-16)
- Restored the existing virtual environment's system-package access and repaired the
  misplaced setuptools helper directory. Original configuration is backed up at
  .venv/pyvenv.cfg.before-voice-repair.
- Restarted Folio with the project interpreter; live status confirms Whisper, Piper
  and BGE/FAISS retrieval are available.
- Whisper transcribed the existing synthetic voice sample correctly:
  "When does my passport expire?" Actual microphone recording remains browser-unverified.
- Direct labelled-field answers now cite source pages and avoid returning whole passages
  for name/date/number questions. Missing or conflicting fields are reported explicitly.
- Dissatisfaction feedback asks for clarification instead of repeating the same excerpt.
- 30 automated tests pass (artifacts/chat-fixes-tests.xml).
- Browser rerun was not executed: automatic approval review timed out.
- Gmail remains unconfigured; no additional model training was needed for these fixes.

## Accounts and reminders update (2026-09-16)
- Signup/login, private account data, persistent conversations and chat continuation implemented.
- Automatic expiry extraction and website reminders implemented, with editable detected dates.
- Verified-account email reminders include retry handling and duplicate suppression.
- 27 automated tests passed; results: artifacts/accounts-tests.xml.
- Live server responds with authentication enabled; anonymous document access returns 401.
- Gmail credentials are not configured and real email delivery has not been tested.
- Updated browser checks have not run: automatic approval review rejected the browser
  rerun because of its usage limit. Older browser results below predate authentication.
- The current virtual environment is incomplete. Tests used system Python; start.ps1
  now checks interpreters and uses one with the required core dependencies.
- Current running configuration uses the baseline classifier, BM25 and Tesseract.
  Earlier optional-model and training results below are historical, not current runtime status.
- See [account and email setup](ACCOUNTS_AND_NOTIFICATIONS.md).

## Earlier build: implemented and exercised
- Responsive document library, drag/drop uploads, filtering, detail dialog and original download.
- Text/native PDF extraction, scanned-image OCR with installed Tesseract.
- Persistent SQLite storage, exact duplicate suppression and complete logical document deletion.
- Labelled-field metadata with offsets and expiry normalization.
- Baseline training: clean and augmented stages, three candidates, validation selection.
- MiniLM: real GPU fine-tuning, six epochs, saved best-validation checkpoint.
- Group-disjoint train/validation/test sets: 768 / 192 / 192 synthetic examples.
- Baseline and MiniLM synthetic test accuracy and macro F1: 1.0.
- BM25 retrieval and BGE-small + FAISS/BM25 hybrid retrieval on six synthetic queries.
- Exact source-excerpt answers and page/document references.
- Confirmed-date reminder creation, deduplication, correction and overdue catch-up.
- Piper synthesis and Whisper-base transcription of one synthetic spoken question: WER 0.
- Jupyter notebook executed end to end; output notebook includes actual training charts.
- Fifteen automated tests passed.
- Headless Edge tested uploads, download, scoped chat, citations, model lab and mobile layout.
  No JavaScript errors; no horizontal overflow at 390 px.

## Implemented but not run with production weights/services
- PaddleOCR 3 adapter: schema test with a stub; local OCR runtime uses Tesseract.
- GLiNER extraction adapter: requires optional package and model.
- BGE-M3 configuration: runtime verification used the smaller BGE-small model.
- Llama/Mistral via Ollama: prompt and citation handling tested with a stub; Ollama not installed.
- IndicTrans2 translation: adapter follows the published interface; gated model access and a
  compatible environment are still needed. No translation quality score is claimed.

## Model and evaluation artifacts
- artifacts/baseline/model.joblib, report.json, split_manifest.json, training_report.png
- artifacts/minilm/model.safetensors, tokenizer/config files, history.json, report.json
- artifacts/evaluation/report.json
- artifacts/optional/report.json and voice_question.wav
- artifacts/browser/report.json and desktop/mobile screenshots
- notebooks/model_training.executed.ipynb

## Accuracy limitations
All training and evaluation examples are synthetic. Perfect scores are expected on this
easy vocabulary-driven dataset and do not establish real-world accuracy. Fitting diagnostics
do not prove the absence of underfitting/overfitting. Representative labelled documents,
real speech, translations and answer-faithfulness annotations are still needed.

## Earlier build environment
The local virtual environment reuses the machine's existing Python packages, including
CUDA PyTorch 2.6.0. Its inherited gTTS package has an unrelated click-version conflict
reported by pip check; this project does not import or use gTTS. Runtime and project tests
passed with the actual environment. For a separate installation, use a clean virtual
environment and the dependencies declared in pyproject.toml.
