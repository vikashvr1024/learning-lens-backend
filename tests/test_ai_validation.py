import pytest

from app.ai.providers.mock import MockProvider
from app.ai.schemas import Diagnosis
from app.ai.service import (
    AIGenerationFailed,
    generate_validated,
    generate_validated_with_fallback,
)
from app.ai.validators import AIOutputValidationError, validate_grounding

EVIDENCE = {
    "concepts": [{"name": "Shadows"}],
    "weaknesses": [{
        "name": "Shadows", "percentage": 20, "question_ids": ["Q1"],
        "reasoning_type": "application",
    }],
    "strengths": [],
    "allowed_concepts": ["Shadows"],
    "options": {"duration_minutes": 30, "question_count": 3,
                "difficulty_counts": {"easy": 1, "medium": 1, "challenging": 1}},
}


def test_unknown_ai_concept_is_rejected():
    output = Diagnosis.model_validate({
        "summary": "Grounded summary", "strengths": [],
        "learning_gaps": [{
            "concept": "Electricity", "severity": "high", "reasoning_type": "recall",
            "evidence": "None", "explanation": "Invented concept",
        }],
        "encouragement": "Keep learning", "teacher_focus": [],
    })
    with pytest.raises(AIOutputValidationError):
        validate_grounding(output, EVIDENCE)


class InvalidProvider(MockProvider):
    name = "test-real-provider"
    model = "test-real-model"
    calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        return {"invalid": True}


@pytest.mark.asyncio
async def test_invalid_ai_output_retries_only_twice_after_initial():
    provider = InvalidProvider()
    with pytest.raises(AIGenerationFailed):
        await generate_validated(
            provider, generation_type="diagnosis", system_prompt="grounding",
            prompt_version="1.0.0", evidence=EVIDENCE, response_schema=Diagnosis,
        )
    assert provider.calls == 3


@pytest.mark.asyncio
async def test_invalid_real_provider_falls_back_to_grounded_output():
    provider = InvalidProvider()
    output, metadata = await generate_validated_with_fallback(
        provider, generation_type="diagnosis", system_prompt="grounding",
        prompt_version="1.0.0", evidence=EVIDENCE, response_schema=Diagnosis,
    )

    assert output.learning_gaps[0].concept == "Shadows"
    assert provider.calls == 3
    assert metadata["provider"] == "mock"
    assert metadata["fallback"] is True
    assert metadata["primary_provider"] == "test-real-provider"
    assert metadata["primary_model"] == "test-real-model"
