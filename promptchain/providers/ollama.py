from __future__ import annotations

import json
import urllib.error
import urllib.request


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        self._model_cache: set[str] | None = None

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = None
        method = "GET"
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"
            headers = {"Content-Type": "application/json"}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Failed to reach Ollama at http://localhost:11434. "
                "Is the Ollama server running?"
            ) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama response was not valid JSON.") from exc

    def list_models(self) -> set[str]:
        if self._model_cache is not None:
            return self._model_cache
        payload = self._request("/api/tags")
        models_raw = payload.get("models", [])
        models: set[str] = set()
        if isinstance(models_raw, list):
            for entry in models_raw:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    models.add(entry["name"])
        self._model_cache = models
        return models

    def ensure_model(self, model: str) -> None:
        models = self.list_models()
        if model not in models:
            available = ", ".join(sorted(models))
            raise RuntimeError(
                f"Model '{model}' not found in Ollama. Available models: {available}"
            )

    def generate(self, model: str, prompt: str) -> str:
        payload = self._request(
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
        )

        if "response" not in payload:
            raise RuntimeError("Ollama response missing 'response' field.")

        return payload["response"]
