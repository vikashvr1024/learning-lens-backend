from typing import Any, Protocol

from pydantic import BaseModel


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        evidence: dict[str, Any],
        response_schema: type[BaseModel],
        feedback: str | None = None,
    ) -> dict[str, Any]: ...

    async def extract_blueprint(
        self,
        *,
        system_prompt: str,
        paper_text: str,
        pdf_bytes: bytes | None,
        filename: str,
    ) -> dict[str, Any]:
        """Draft a blueprint JSON object from a test paper.

        Providers without document vision must use paper_text and raise
        RuntimeError when it is empty (e.g. scanned-image PDFs).
        """
        ...

