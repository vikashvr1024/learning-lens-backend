import hashlib
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.interface import AIProvider
from app.ai.validators import AIOutputValidationError, validate_grounding

logger = logging.getLogger(__name__)


class AIGenerationFailed(RuntimeError):
    pass


def evidence_fingerprint(evidence: dict[str, Any], generation_type: str, model: str) -> str:
    canonical = json.dumps(
        {"evidence": evidence, "generation_type": generation_type, "model": model},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def generate_validated(
    provider: AIProvider,
    *,
    generation_type: str,
    system_prompt: str,
    prompt_version: str,
    evidence: dict[str, Any],
    response_schema: type[BaseModel],
) -> tuple[BaseModel, dict[str, Any]]:
    feedback: str | None = None
    started = time.perf_counter()
    failures: list[str] = []
    for attempt in range(3):
        try:
            raw = await provider.generate_structured(
                system_prompt=system_prompt, evidence=evidence,
                response_schema=response_schema, feedback=feedback,
            )
            output = response_schema.model_validate(raw)
            validate_grounding(output, evidence)
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            metadata = {
                "provider": provider.name, "model": provider.model,
                "prompt_version": prompt_version, "latency_ms": latency_ms,
                "attempts": attempt + 1, "success": True,
            }
            logger.info("ai_generation", extra=metadata)
            return output, metadata
        except (ValidationError, AIOutputValidationError, ValueError, json.JSONDecodeError) as error:
            feedback = f"Validation failed: {error}. Regenerate using only allowed concepts and the exact schema."
            failures.append(str(error))
    metadata = {
        "provider": provider.name, "model": provider.model,
        "prompt_version": prompt_version,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "attempts": 3, "success": False, "validation_errors": failures,
    }
    logger.warning("ai_generation_failed", extra=metadata)
    raise AIGenerationFailed("AI generation failed validation.")

