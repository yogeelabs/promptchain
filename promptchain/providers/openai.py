from __future__ import annotations

from promptchain.llm_openai import generate as openai_generate


class OpenAIProvider:
    def __init__(self) -> None:
        self.api_key = None

    def ensure_model(self, model: str) -> None:
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError("OpenAI model name must be a non-empty string.")

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 300,
        extra: dict | None = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        return openai_generate(
            messages=messages,
            model=model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            extra=extra,
        )
