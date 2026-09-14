from collections import Counter
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.evidence import build_evidence
from app.ai.factory import get_ai_provider
from app.ai.schemas import Diagnosis, LessonPlan, Recommendations, WorksheetOutput
from app.ai.service import evidence_fingerprint, generate_validated_with_fallback
from app.ai.validators import validate_grounding
from app.core.config import Settings
from app.models import AIGeneration, StudentAssessment, Worksheet
from app.prompts.diagnostic import DIAGNOSTIC_PROMPT_VERSION, DIAGNOSTIC_SYSTEM_PROMPT
from app.prompts.lesson_plan import LESSON_PLAN_PROMPT_VERSION, LESSON_PLAN_SYSTEM_PROMPT
from app.prompts.recommendations import (
    RECOMMENDATIONS_PROMPT_VERSION,
    RECOMMENDATIONS_SYSTEM_PROMPT,
)
from app.prompts.worksheet import WORKSHEET_PROMPT_VERSION, WORKSHEET_SYSTEM_PROMPT
from app.schemas.analysis import StudentAnalysis
from app.schemas.blueprint import Blueprint

GENERATION_CONFIG = {
    "diagnosis": (Diagnosis, DIAGNOSTIC_SYSTEM_PROMPT, DIAGNOSTIC_PROMPT_VERSION),
    "recommendations": (Recommendations, RECOMMENDATIONS_SYSTEM_PROMPT, RECOMMENDATIONS_PROMPT_VERSION),
    "lesson_plan": (LessonPlan, LESSON_PLAN_SYSTEM_PROMPT, LESSON_PLAN_PROMPT_VERSION),
    "worksheet": (WorksheetOutput, WORKSHEET_SYSTEM_PROMPT, WORKSHEET_PROMPT_VERSION),
}

WORKSHEET_BATCH_SIZE = 12
DIFFICULTY_PATTERN = (
    "easy", "medium", "medium", "easy", "challenging",
    "medium", "easy", "medium", "challenging", "medium",
)


def _difficulty_schedule(counts: dict[str, int]) -> list[str]:
    remaining = counts.copy()
    schedule: list[str] = []
    while any(remaining.values()):
        for level in DIFFICULTY_PATTERN:
            if remaining[level] > 0:
                schedule.append(level)
                remaining[level] -= 1
    return schedule


async def _generate_worksheet(
    provider,
    evidence: dict[str, Any],
    prompt: str,
    version: str,
) -> tuple[WorksheetOutput, dict[str, Any]]:
    total = evidence["options"]["question_count"]
    allowed = evidence["allowed_concepts"]
    concept_schedule = [allowed[index % len(allowed)] for index in range(total)]
    difficulties = _difficulty_schedule(evidence["options"]["difficulty_counts"])
    batch_total = (total + WORKSHEET_BATCH_SIZE - 1) // WORKSHEET_BATCH_SIZE
    outputs: list[WorksheetOutput] = []
    batch_metadata: list[dict[str, Any]] = []

    for batch_index, offset in enumerate(range(0, total, WORKSHEET_BATCH_SIZE), start=1):
        batch_count = min(WORKSHEET_BATCH_SIZE, total - offset)
        batch_concepts = list(dict.fromkeys(concept_schedule[offset:offset + batch_count]))
        batch_difficulties = difficulties[offset:offset + batch_count]
        batch_evidence = deepcopy(evidence)
        batch_evidence["allowed_concepts"] = batch_concepts
        batch_evidence["required_practice_concepts"] = batch_concepts
        batch_evidence["previous_worksheet_questions"] = [
            question.question
            for output in outputs
            for question in output.questions
        ]
        difficulty_counts = Counter(batch_difficulties)
        batch_evidence["options"].update({
            "question_count": batch_count,
            "difficulty_counts": {
                level: difficulty_counts[level]
                for level in ("easy", "medium", "challenging")
            },
            "question_id_start": offset + 1,
            "batch_number": batch_index,
            "batch_total": batch_total,
        })
        output, metadata = await generate_validated_with_fallback(
            provider,
            generation_type="worksheet",
            system_prompt=prompt,
            prompt_version=version,
            evidence=batch_evidence,
            response_schema=WorksheetOutput,
        )
        outputs.append(output)
        batch_metadata.append(metadata)

    questions = []
    for output in outputs:
        for question in output.questions:
            questions.append(question.model_copy(update={"id": f"W{len(questions) + 1}"}))
    merged = WorksheetOutput(
        title=f"{evidence['assessment']['title']} - Complete Revision Worksheet",
        student_name=outputs[0].student_name,
        target_concepts=list(dict.fromkeys(question.concept for question in questions)),
        instructions=(
            f"Complete all {total} questions. Start with the easy questions, then work through "
            "the medium and challenging questions. Try every question before opening its "
            "step-by-step solution."
        ),
        questions=questions,
    )
    validate_grounding(merged, evidence)
    fallback_batches = [
        index for index, metadata in enumerate(batch_metadata, start=1)
        if metadata.get("fallback")
    ]
    metadata = {
        "provider": provider.name if not fallback_batches else "mixed",
        "model": provider.model,
        "prompt_version": version,
        "latency_ms": sum(item.get("latency_ms", 0) for item in batch_metadata),
        "attempts": sum(item.get("attempts", 1) for item in batch_metadata),
        "success": True,
        "batch_count": batch_total,
        "fallback": bool(fallback_batches),
        "fallback_batches": fallback_batches,
        "batches": batch_metadata,
    }
    return merged, metadata


async def generate_artifact(
    db: Session,
    item: StudentAssessment,
    generation_type: str,
    settings: Settings,
    *,
    force: bool = False,
    duration_minutes: int = 30,
    question_count: int = 8,
) -> dict[str, Any]:
    schema, prompt, version = GENERATION_CONFIG[generation_type]
    blueprint = Blueprint.model_validate(item.assessment.blueprint_json)
    analysis = StudentAnalysis.model_validate(item.analysis_json)
    evidence = build_evidence(
        blueprint, analysis, duration_minutes=duration_minutes, question_count=question_count
    )
    provider = get_ai_provider(settings)
    fingerprint = evidence_fingerprint(
        evidence, generation_type, provider.model, prompt_version=version
    )
    if not force:
        cached = db.scalar(
            select(AIGeneration).where(
                AIGeneration.student_assessment_id == item.id,
                AIGeneration.generation_type == generation_type,
                AIGeneration.input_fingerprint == fingerprint,
            ).order_by(AIGeneration.created_at.desc())
        )
        if cached:
            return {"id": cached.id, "type": generation_type, "content": cached.structured_output, "cached": True}
    if generation_type == "worksheet":
        output, metadata = await _generate_worksheet(provider, evidence, prompt, version)
    else:
        output, metadata = await generate_validated_with_fallback(
            provider, generation_type=generation_type, system_prompt=prompt,
            prompt_version=version, evidence=evidence, response_schema=schema,
        )
    record = AIGeneration(
        student_assessment_id=item.id, generation_type=generation_type,
        provider=metadata["provider"], model=metadata["model"], prompt_version=version,
        input_fingerprint=fingerprint, structured_output=output.model_dump(mode="json"),
        validation_metadata=metadata,
    )
    db.add(record)
    if generation_type == "worksheet":
        db.add(Worksheet(student_assessment_id=item.id, content_json=output.model_dump(mode="json")))
    db.commit()
    db.refresh(record)
    return {"id": record.id, "type": generation_type, "content": record.structured_output, "cached": False}
