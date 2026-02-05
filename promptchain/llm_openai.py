from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _resolve_base_url() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return base_url.rstrip("/")


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    organization = os.getenv("OPENAI_ORGANIZATION")
    project = os.getenv("OPENAI_PROJECT")
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project
    return headers


def _request(path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when using the OpenAI provider.")

    base_url = _resolve_base_url()
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=_build_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        message = f"HTTP {exc.code}"
        if body:
            try:
                parsed = json.loads(body)
                error = parsed.get("error", {})
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


def _extract_text(payload: dict[str, Any]) -> str:
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


def generate(
    *,
    messages: list[dict[str, Any]],
    model: str,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    timeout: int = 300,
    extra: dict[str, Any] | None = None,
) -> str:
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("OpenAI messages must be a non-empty list.")

    body: dict[str, Any] = {
        "model": model,
        "input": messages,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    if extra:
        body.update(extra)

    try:
        payload = _request("/responses", body, timeout)
    except RuntimeError as exc:
        if reasoning_effort:
            raise RuntimeError(f"OpenAI rejected reasoning.effort: {exc}") from exc
        raise
    return _extract_text(payload)
