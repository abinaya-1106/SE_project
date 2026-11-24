import os
import re
import time
from datetime import datetime

import httpx                      # installed automatically with the openai package
from pypdf import PdfReader

import config

_http = httpx.Client(timeout=httpx.Timeout(900.0, connect=10.0))


def load_documents(domain: str) -> str:
    """Read all .txt/.pdf files in data/<domain>/ and join them.
    The character budget is split evenly across files, so every file
    contributes an excerpt instead of the last files being cut off."""
    folder = os.path.join("data", domain)
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Folder not found: {folder}")

    docs = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        text = ""
        if name.lower().endswith(".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif name.lower().endswith(".pdf"):
            reader = PdfReader(path)
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            continue
        text = re.sub(r"\s+", " ", text).strip()   # collapse whitespace = fewer tokens
        docs.append((name, text))

    if not docs:
        raise ValueError(f"No .txt or .pdf files found in {folder}")

    per_file = max(300, config.MAX_DOC_CHARS // len(docs))
    parts = []
    for name, text in docs:
        if len(text) > per_file:
            text = text[:per_file].rsplit(" ", 1)[0] + " ..."
        parts.append(f"=== DOCUMENT: {name} ===\n{text}")
    return "\n\n".join(parts)


def ask_llm(system_prompt: str, user_prompt: str, json_mode: bool = False,
            max_tokens: int = None, stop: list = None) -> str:
    """Send a prompt to the local Ollama model using its native /api/chat endpoint."""
    payload = {
        "model": config.MODEL,
        "messages": [
            # "/no_think" is a fallback for Qwen3's reasoning mode
            {"role": "system", "content": system_prompt + " /no_think"},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,                      # properly disables Qwen3 thinking
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "temperature": config.TEMPERATURE,
            "num_ctx": config.NUM_CTX,
            "num_predict": max_tokens or config.MAX_TOKENS,
        },
    }
    if json_mode:
        payload["format"] = "json"
    if stop:
        payload["options"]["stop"] = stop

    start = time.time()
    resp = _http.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()
    text = (data.get("message") or {}).get("content", "") or ""

    out_tokens = data.get("eval_count", 0)
    print(f"    (LLM call: {time.time() - start:.1f}s, {out_tokens} tokens generated)")

    # remove any reasoning block that still slips through
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def warm_up():
    """Load the model into memory so the first real call isn't slow."""
    try:
        _http.post(f"{config.OLLAMA_URL}/api/generate",
                   json={"model": config.MODEL, "prompt": "", "keep_alive": config.KEEP_ALIVE})
    except Exception as e:
        print(f"[!] Warm-up skipped: {e}")


def save_output(filename_prefix: str, content: str) -> str:
    """Save text to outputs/ with a timestamp. Returns the file path."""
    os.makedirs("outputs", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join("outputs", f"{filename_prefix}_{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path