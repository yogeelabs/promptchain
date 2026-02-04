from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class OpenAIProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when using the OpenAI provider."
            )
        self.base_url = "https://api.openai.com/v1"
        self.organization = os.getenv("OPENAI_ORGANIZATION")
        self.project = os.getenv("OPENAI_PROJECT")

    def ensure_model(self, model: str) -> None:
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError("OpenAI model name must be a non-empty string.")

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project

        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            message = f"HTTP {exc.code}"
            if body:
                try:
                    payload = json.loads(body)
                    error = payload.get("error", {})
                    if isinstance(error, dict) and isinstance(error.get("message"), str):
                        message = error["message"]
                except json.JSONDecodeError:
                    message = body
            raise RuntimeError(f"OpenAI request failed: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Failed to reach OpenAI API.") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI response was not valid JSON.") from exc

    def generate(self, model: str, prompt: str) -> str:
        payload = self._request(
            "/responses",
            {
                "model": model,
                "input": prompt,
            },
        )

        output = payload.get("output")
        if not isinstance(output, list):
            raise RuntimeError("OpenAI response missing 'output' list.")

        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") not in {"output_text", "text"}:
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)

        if not texts:
            raise RuntimeError("OpenAI response contained no text output.")

        return "\n".join(texts)
