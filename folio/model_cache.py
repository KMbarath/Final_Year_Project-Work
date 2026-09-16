from pathlib import Path


def cached_model_path(name):
    """Prefer already downloaded weights so offline inference performs no HTTP probes."""
    if Path(name).exists():
        return name
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        path = Path(snapshot_download(name, local_files_only=True))
    except LocalEntryNotFoundError:
        return name
    weights = any((path / filename).exists() for filename in
                  ["model.safetensors", "pytorch_model.bin", "model.safetensors.index.json"])
    return str(path) if weights else name
