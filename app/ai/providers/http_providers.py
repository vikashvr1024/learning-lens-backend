import asyncio
import base64
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel


def _json_from_text(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("AI output must be a JSON object")
    return parsed


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url, timeout

    async def generate_structured(
        self, *, system_prompt: str, evidence: dict[str, Any],
        response_schema: type[BaseModel], feedback: str | None = None,
    ) -> dict[str, Any]:
        prompt = json.dumps({"evidence": evidence, "schema": response_schema.model_json_schema(), "feedback": feedback})
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
        return _json_from_text(response.json()["choices"][0]["message"]["content"])

    async def extract_blueprint(
        self, *, system_prompt: str, paper_text: str,
        pdf_bytes: bytes | None, filename: str, feedback: str | None = None,
    ) -> dict[str, Any]:
        if not paper_text.strip():
            raise RuntimeError(
                "This provider needs readable PDF text; scanned papers require AI_PROVIDER=gemini."
            )
        prompt = json.dumps({"paper_text": paper_text, "source_file": filename, "feedback": feedback})
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"The AI provider could not read the paper: {error}.") from error
        return _json_from_text(response.json()["choices"][0]["message"]["content"])


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: int):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    async def generate_structured(
        self, *, system_prompt: str, evidence: dict[str, Any],
        response_schema: type[BaseModel], feedback: str | None = None,
    ) -> dict[str, Any]:
        prompt = json.dumps({"evidence": evidence, "schema": response_schema.model_json_schema(), "feedback": feedback})
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": self.model, "max_tokens": 4096, "temperature": 0.2, "system": system_prompt,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
        return _json_from_text(response.json()["content"][0]["text"])

    async def extract_blueprint(
        self, *, system_prompt: str, paper_text: str,
        pdf_bytes: bytes | None, filename: str, feedback: str | None = None,
    ) -> dict[str, Any]:
        if not paper_text.strip():
            raise RuntimeError(
                "This provider needs readable PDF text; scanned papers require AI_PROVIDER=gemini."
            )
        prompt = json.dumps({"paper_text": paper_text, "source_file": filename, "feedback": feedback})
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": self.model, "max_tokens": 8192, "temperature": 0.1, "system": system_prompt,
                          "messages": [{"role": "user", "content": prompt}]},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"The AI provider could not read the paper: {error}.") from error
        return _json_from_text(response.json()["content"][0]["text"])


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: int):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with retries for transient Gemini overloads (HTTP 500/503).

        Quota errors (HTTP 429) and bad requests are raised immediately with an
        actionable message instead of being retried.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, params={"key": self.api_key}, json=payload)
                    response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as error:
                raise RuntimeError("The AI provider timed out. Please try again.") from error
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status == 429:
                    raise RuntimeError(
                        "The AI key hit its Gemini quota/rate limit (HTTP 429). "
                        "Wait a minute and try again, or check usage in Google AI Studio."
                    ) from error
                if status in (500, 503) and attempt < 2:
                    last_error = error
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if status in (500, 503):
                    raise RuntimeError(
                        "Gemini is overloaded right now (HTTP "
                        f"{status}). Wait a minute and try again."
                    ) from error
                raise RuntimeError(
                    f"The AI provider rejected the request (HTTP {status}). "
                    "Check AI_MODEL and AI_API_KEY."
                ) from error
        assert last_error is not None
        raise RuntimeError("Gemini is overloaded right now. Wait a minute and try again.") from last_error

    async def generate_structured(
        self, *, system_prompt: str, evidence: dict[str, Any],
        response_schema: type[BaseModel], feedback: str | None = None,
    ) -> dict[str, Any]:
        prompt = json.dumps({"instructions": system_prompt, "evidence": evidence, "feedback": feedback})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = await self._post(url, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema.model_json_schema(),
            },
        })
        return _json_from_text(data["candidates"][0]["content"]["parts"][0]["text"])

    async def extract_blueprint(
        self, *, system_prompt: str, paper_text: str,
        pdf_bytes: bytes | None, filename: str, feedback: str | None = None,
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        if pdf_bytes:
            parts.append({"inline_data": {
                "mime_type": "application/pdf",
                "data": base64.b64encode(pdf_bytes).decode("ascii"),
            }})
        parts.append({"text": json.dumps({"paper_text": paper_text, "source_file": filename, "feedback": feedback})})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = await self._post(url, {
            "contents": [{"parts": parts}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8192,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
            },
        })
        return _json_from_text(data["candidates"][0]["content"]["parts"][0]["text"])
