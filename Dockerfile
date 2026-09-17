FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY folio ./folio
COPY training ./training
COPY prompts.yaml ./prompts.yaml
COPY artifacts/voices ./artifacts/voices
RUN pip install --no-cache-dir ".[voice]" matplotlib \
	&& python -c "import whisper; whisper.load_model('tiny', download_root='/app/.cache/whisper')" \
	&& python -c "from training.data import generate; generate('data/synthetic/documents.csv')" \
	&& python -m training.baseline --dataset data/synthetic/documents.csv --output artifacts/baseline \
	&& pip uninstall -y matplotlib
RUN mkdir -p /data
ENV FOLIO_DATA_DIR=/data
ENV FOLIO_WHISPER_MODEL=tiny
ENV FOLIO_PIPER_MODEL=/app/artifacts/voices/en_US-lessac-medium.onnx
CMD ["sh", "-c", "uvicorn folio.api:app --host 0.0.0.0 --port ${PORT}"]
