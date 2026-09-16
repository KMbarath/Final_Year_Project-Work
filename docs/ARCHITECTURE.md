# Architecture

~~~mermaid
flowchart LR
    U[PDF / image / text] --> X[Native extraction or OCR]
    X --> C[Saved document classifier]
    X --> E[Entity extraction]
    X --> D[(SQLite: original, pages, metadata)]
    C --> D
    E --> D
    D --> K[Page-preserving chunks]
    K --> B[BM25]
    K --> V[Optional BGE + FAISS]
    B --> R[Rank fusion]
    V --> R
    Q[Typed question / Whisper] --> R
    R --> A[Source excerpts / local Ollama]
    A --> T[Optional IndicTrans2]
    T --> O[Answer and source passages]
    O --> P[Optional Piper]
    D --> N[Confirmed expiry checks]
~~~

FastAPI serves a dependency-free HTML/CSS/JavaScript interface and REST API.
Heavy models load lazily; inference access is serialized for this 4 GB GPU workstation.
Classifier training is separate from serving. The default classifier is the trained
TF-IDF model; the start script can select the trained MiniLM artifact.

SQLite stores documents and originals transactionally. Retrieval rebuilds in-memory
indices when document content changes. Page provenance is preserved through chunking.
Uploads use content hashes to suppress exact duplicates. No uploaded filenames become
filesystem paths. Original downloads use attachment disposition.

A lifespan task runs reminders hourly. GET /api/reminders also runs a catch-up check.
Only confirmed dates produce notifications; corrections remove stale notifications.
The application does not send email or other external messages.

The local-origin/host policy and safe DOM text rendering protect the intended personal
desktop workflow. The server is not a public multi-user deployment.

The original PDF architecture lists pretrained foundation components, not datasets
suitable for retraining them. This project fine-tunes the task-specific classifier;
other components have usable adapters and explicit setup/measurement requirements.
