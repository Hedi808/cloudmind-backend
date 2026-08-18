from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel


@dataclass
class StructuredLLMResult:
    parsed: BaseModel
    provider: str
    model: str
    response_id: str | None = None
    usage: dict[str, int | None] = field(default_factory=dict)


class StructuredLLMProvider(Protocol):
    provider_name: str
    model: str

    @property
    def available(self) -> bool: ...

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> StructuredLLMResult: ...


class OpenAIResponsesProvider:
    """Structured-output adapter for the OpenAI Responses API."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: int = 60,
        reasoning_effort: str = "medium",
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.api_key or self._client is not None)

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> StructuredLLMResult:
        client = self._client or self._create_client()
        response = client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=response_model,
            reasoning={"effort": self.reasoning_effort},
            store=False,
        )

        parsed = getattr(response, "output_parsed", None)

        if parsed is None:
            raise ValueError("The LLM response did not contain structured planner output.")

        if not isinstance(parsed, response_model):
            parsed = response_model.model_validate(parsed)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None

        return StructuredLLMResult(
            parsed=parsed,
            provider=self.provider_name,
            model=self.model,
            response_id=getattr(response, "id", None),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        )

    def _create_client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Run pip install -r requirements.txt."
            ) from exc

        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )


class GeminiStructuredProvider:
    """Structured-output adapter for Gemini's OpenAI-compatible API."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: int = 60,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.api_key or self._client is not None)

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> StructuredLLMResult:
        client = self._client or self._create_client()
        completion = client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
        )
        choices = getattr(completion, "choices", None) or []

        if not choices:
            raise ValueError("The Gemini response did not contain a completion choice.")

        parsed = getattr(choices[0].message, "parsed", None)

        if parsed is None:
            raise ValueError("The Gemini response did not contain structured planner output.")

        if not isinstance(parsed, response_model):
            parsed = response_model.model_validate(parsed)

        usage = getattr(completion, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None

        return StructuredLLMResult(
            parsed=parsed,
            provider=self.provider_name,
            model=self.model,
            response_id=getattr(completion, "id", None),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        )

    def _create_client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Run pip install -r requirements.txt."
            ) from exc

        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )


class OllamaStructuredProvider:
    """Structured-output adapter for a locally running Ollama server."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout_seconds: int = 120,
        requester: Any | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._requester = requester

    @property
    def available(self) -> bool:
        # Ollama needs no credential. A real generation verifies that the local
        # service is running and that the selected model has been downloaded.
        return bool(self.model and self.base_url)

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> StructuredLLMResult:
        schema = response_model.model_json_schema()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\n"
                        "Return JSON matching this schema exactly:\n"
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
            ],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
        }
        response = self._send(payload)
        message = response.get("message") or {}
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama did not return structured response content.")

        parsed = response_model.model_validate_json(content)
        input_tokens = response.get("prompt_eval_count")
        output_tokens = response.get("eval_count")
        total_tokens = (
            input_tokens + output_tokens
            if isinstance(input_tokens, int) and isinstance(output_tokens, int)
            else None
        )

        return StructuredLLMResult(
            parsed=parsed,
            provider=self.provider_name,
            model=self.model,
            response_id=None,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        )

    def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._requester is not None:
            return self._requester(payload)

        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(
                "Ollama is not reachable at "
                f"{self.base_url}. Start Ollama and pull model {self.model}."
            ) from exc
