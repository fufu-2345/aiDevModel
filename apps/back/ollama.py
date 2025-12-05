import os
import json
import requests
import shutil
import subprocess
from typing import List, Optional

MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")


def list_models() -> List[str]:
    """Return a list of model names available to the local Ollama installation.

    This calls the `ollama list` CLI and parses the NAME column. It returns
    items like 'llama3.2:latest'. If the CLI is not available, returns an
    empty list.
    """
    bin_path = shutil.which("ollama")
    if not bin_path:
        return []
    try:
        out = subprocess.check_output([bin_path, "list"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    models = []
    lines = [l for l in out.splitlines() if l.strip()]
    # Skip header if present (starts with NAME)
    for line in lines:
        if line.strip().startswith("NAME"):
            continue
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def generate_text(prompt: str, model: Optional[str] = None, timeout: int = 30) -> str:
    """Generate text using local Ollama HTTP API.

    - `model` overrides the `OLLAMA_MODEL` env var if provided.
    - Returns concatenated streaming response (handles NDJSON stream).
    """
    use_model = model or os.environ.get("OLLAMA_MODEL", MODEL)
    payload = {"model": use_model, "prompt": prompt}
    try:
        r = requests.post(URL, json=payload, stream=True, timeout=timeout)
    except Exception as e:
        return f"error calling ollama: {e}"

    if r.status_code != 200:
        try:
            return r.text
        except Exception:
            return f"ollama returned status {r.status_code}"

    parts = []
    try:
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            resp = obj.get("response")
            if resp:
                parts.append(resp)
            if obj.get("done"):
                break
    except Exception as e:
        return f"error reading ollama stream: {e}"

    return "".join(parts)