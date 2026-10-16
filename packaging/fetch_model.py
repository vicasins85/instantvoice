"""Downloads the Whisper model so it ships inside the installer. Run from companion/."""
import sys

from huggingface_hub import snapshot_download

size = sys.argv[1] if len(sys.argv) > 1 else "base"
path = snapshot_download(f"Systran/faster-whisper-{size}", local_dir=f"models/{size}")
print("model ready at", path)
