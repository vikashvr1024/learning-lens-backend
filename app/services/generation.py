from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.evidence import build_evidence
from app.ai.factory import get_ai_provider
from app.ai.schemas import Diagnosis, LessonPlan, Recommendations, WorksheetOutput
from app.ai.service import evidence_fingerprint, generate_validated
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
    fingerprint = evidence_fingerprint(evidence, generation_type, provider.model)
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
    output, metadata = await generate_validated(
        provider, generation_type=generation_type, system_prompt=prompt,
        prompt_version=version, evidence=evidence, response_schema=schema,
    )
    record = AIGeneration(
        student_assessment_id=item.id, generation_type=generation_type,
        provider=provider.name, model=provider.model, prompt_version=version,
        input_fingerprint=fingerprint, structured_output=output.model_dump(mode="json"),
        validation_metadata=metadata,
    )
    db.add(record)
    if generation_type == "worksheet":
        db.add(Worksheet(student_assessment_id=item.id, content_json=output.model_dump(mode="json")))
    db.commit()
    db.refresh(record)
    return {"id": record.id, "type": generation_type, "content": record.structured_output, "cached": False}

