from __future__ import annotations

from promptchain import llm_openai


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
        return llm_openai.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            extra=extra,
        )

    def upload_batch_file(self, path: str) -> dict:
        return llm_openai.upload_file(path=path, purpose="batch")

    def create_batch(self, input_file_id: str, *, metadata: dict | None = None) -> dict:
        return llm_openai.create_batch(
            input_file_id=input_file_id, endpoint="/v1/responses", metadata=metadata
        )

    def retrieve_batch(self, batch_id: str) -> dict:
        return llm_openai.retrieve_batch(batch_id)

    def download_file(self, file_id: str) -> str:
        return llm_openai.download_file_content(file_id)

    def extract_text(self, payload: dict) -> str:
        return llm_openai.extract_text_from_response_payload(payload)
