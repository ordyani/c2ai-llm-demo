"""
C2AI containerized demo: a long-running service that (a) serves a health
endpoint on PORT and (b) keeps calling the LLM gateway in the background so
Athena can price the usage.

Runs forever (unlike the CI version), which is what a containerized deployment
needs: the pod stays Running, produces metrics, and keeps generating gateway
usage. Standard library only — no pip install.

Env:
  PORT              health server port                (default 8080)
  LLM_ENDPOINT      gateway chat/completions URL
  LLM_API_TOKEN     gateway API key
  LLM_MODEL_NAME    priced model: qwen3-6 / gpt-4o / claude-sonnet-5 ...
  BATCH_SIZE        requests per batch                (default 5)
  BATCH_INTERVAL    seconds between batches           (default 60)
  PROMPT            user prompt
"""

import datetime
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"last_batch": None, "ok": 0, "failed": 0}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except ValueError:
        return default


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(STATE).encode())

    def log_message(self, *_args):  # silence per-request logging
        return


def serve_health(port: int) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


def chat_once(endpoint: str, token: str, model: str, prompt: str) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
    }).encode()
    request = urllib.request.Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def main() -> None:
    port = env_int("PORT", 8080)
    endpoint = os.environ.get("LLM_ENDPOINT", "").strip()
    token = os.environ.get("LLM_API_TOKEN", "").strip()
    model = os.environ.get("LLM_MODEL_NAME", "gpt-4o").strip()
    batch_size = env_int("BATCH_SIZE", 5)
    batch_interval = env_int("BATCH_INTERVAL", 60)
    prompt = os.environ.get("PROMPT", "In one sentence, what is Kubernetes?").strip()

    threading.Thread(target=serve_health, args=(port,), daemon=True).start()
    print(f"health server on :{port}; model={model} batch_size={batch_size} interval={batch_interval}s")

    if not endpoint or not token:
        print("WARNING: LLM_ENDPOINT / LLM_API_TOKEN not set — serving health only, no gateway calls")

    while True:
        if endpoint and token:
            for _ in range(batch_size):
                try:
                    result = chat_once(endpoint, token, model, prompt)
                    usage = result.get("usage", {}) or {}
                    STATE["ok"] += 1
                    print(f"ok: prompt_tokens={usage.get('prompt_tokens')} "
                          f"completion_tokens={usage.get('completion_tokens')}")
                except Exception as exc:  # noqa: BLE001
                    STATE["failed"] += 1
                    print(f"error: {type(exc).__name__}: {exc}")
            STATE["last_batch"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        time.sleep(batch_interval)


if __name__ == "__main__":
    main()
