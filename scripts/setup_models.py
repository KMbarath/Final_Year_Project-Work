"""Download optional public models to the workspace; no personal documents are sent."""
import os
from pathlib import Path
import argparse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME",str(ROOT/".cache/huggingface"))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--embedding",default="BAAI/bge-small-en-v1.5")
    p.add_argument("--whisper",default="base")
    args=p.parse_args()
    from sentence_transformers import SentenceTransformer
    import whisper
    folder=ROOT/"artifacts/voices"
    folder.mkdir(parents=True,exist_ok=True)
    for suffix in [".onnx",".onnx.json"]:
        name="en_US-lessac-medium"+suffix
        destination=folder/name
        if not destination.exists():
            url="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"+name
            print("Downloading",name,flush=True)
            temporary=destination.with_suffix(destination.suffix+".part")
            urllib.request.urlretrieve(url,temporary)
            temporary.replace(destination)
    print("Downloading embedding model",args.embedding,flush=True)
    SentenceTransformer(args.embedding,device="cpu")
    print("Downloading Whisper",args.whisper,flush=True)
    whisper.load_model(args.whisper,device="cpu",download_root=str(ROOT/".cache/whisper"))
    print("Optional models ready.",flush=True)


if __name__=="__main__":
    main()
