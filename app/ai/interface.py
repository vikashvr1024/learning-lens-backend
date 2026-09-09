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

