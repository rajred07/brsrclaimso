"""Small configurable JSON client with raw response/run provenance and caching."""
import hashlib
import json
import os
import platform
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path=ROOT / "config.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def read_key(settings):
    variable = settings["api_key_env"]
    key = os.getenv(variable)
    if not key and settings.get("env_file"):
        path = ROOT / settings["env_file"]
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == variable:
                    key = value.strip().strip("\"'")
    if not key:
        raise RuntimeError(f"Set {variable} in the environment or configured local env_file")
    return key


def environment_record():
    return {"python": platform.python_version(), "libraries":
            {name: version(name) for name in ("PyMuPDF", "PyYAML", "requests")}}


class JSONClient:
    def __init__(self, config):
        self.config = config
        self.settings = config["llm"]
        self.last_call = 0.0

    def generate(self, prompt, purpose):
        settings = self.settings
        if not settings.get("model"):
            raise ValueError("An exact model identifier is required")
        identity = {"prompt": prompt, "purpose": purpose, "settings": settings,
                    "prompt_version": self.config["prompts"]["version"]}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        directory = ROOT / settings["cache_directory"]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            return json.loads(record["text"]), {"cache_hit": True, "run_id": digest,
                                                "runtime_ms": 0, "model": record.get("resolved_model")}
        key = read_key(settings)
        wait = 60 / float(settings.get("requests_per_minute", 5)) - (time.monotonic() - self.last_call)
        if wait > 0:
            time.sleep(min(wait, 60))
        self.last_call = time.monotonic()
        started = time.perf_counter()
        if settings["provider"] == "gemini":
            url = settings["base_url"].rstrip("/") + "/models/" + settings["model"].removeprefix("models/") + ":generateContent"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": settings["temperature"],
                                            "maxOutputTokens": settings["max_output_tokens"],
                                            "responseMimeType": "application/json"}}
            headers = {"x-goog-api-key": key}
        elif settings["provider"] == "json_endpoint":
            url = settings["base_url"]
            payload = {"model": settings["model"], "prompt": prompt,
                       "temperature": settings["temperature"], "max_output_tokens": settings["max_output_tokens"]}
            headers = {"Authorization": f"Bearer {key}"}
        else:
            raise ValueError("provider must be gemini or json_endpoint")
        try:
            for attempt in range(3):
                response = requests.post(url, headers=headers, json=payload, timeout=settings.get("timeout_seconds", 60))
                if response.status_code not in {502, 503, 504} or attempt == 2:
                    break
                time.sleep(5 * (attempt + 1))
        except requests.RequestException as exc:
            raise RuntimeError("LLM network request failed; no prediction was recorded") from exc
        elapsed = (time.perf_counter() - started) * 1000
        if not response.ok:
            # Keys never appear in URLs, logs or stored configuration.
            error = {"status_code": response.status_code, "body": response.text,
                     "requested_model": settings["model"], "run_date": datetime.now(timezone.utc).isoformat()}
            (directory / f"{digest}.error.json").write_text(json.dumps(error, indent=2), encoding="utf-8")
            raise RuntimeError(f"LLM HTTP {response.status_code}; see {digest}.error.json. No fallback or fabricated verdict.")
        raw = response.json()
        if settings["provider"] == "gemini":
            candidates = raw.get("candidates", [])
            if not candidates or candidates[0].get("finishReason") not in {None, "STOP"}:
                raise RuntimeError("Blocked or incomplete LLM response; no prediction recorded")
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []) if not p.get("thought"))
            resolved = raw.get("modelVersion")
        else:
            text, resolved = raw["text"], raw.get("model")
        parsed = json.loads(text)  # reject Markdown or invalid JSON rather than silently repair
        record = {**identity, "run_id": digest, "run_date": datetime.now(timezone.utc).isoformat(),
                  "resolved_model": resolved, "runtime_ms": elapsed, "attempts": attempt + 1, "environment": environment_record(),
                  "text": text, "raw_response": raw}
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return parsed, {"cache_hit": False, "run_id": digest, "runtime_ms": elapsed, "model": resolved}
