import json

import httpx
from sqlalchemy.orm import Session

from app.ai.factory import get_ai_provider
from app.core.config import Settings
from app.ingestion.blueprint import parse_blueprint
from app.ingestion.errors import IngestionError, IngestionIssue
from app.ingestion.pdf_text import extract_pdf_text
from app.models import Assessment
from app.prompts.blueprint_extraction import BLUEPRINT_EXTRACTION_SYSTEM_PROMPT
from app.schemas.blueprint import Blueprint
from app.services.assessments import assessment_summary, save_blueprint

MAX_EXTRACTION_ATTEMPTS = 3


def _describe(error: IngestionError) -> str:
    details = "; ".join(
        f"[{issue.code}] {issue.message}" + (f" at {issue.column}" if issue.column else "")
        for issue in error.issues
    )
    return f"{error} {details}".strip()


def _normalize_totals(draft: dict) -> bool:
    """Set assessment.total_marks to the exact sum of question max_marks.

    Small models reliably mis-add totals, so arithmetic is done here
    deterministically instead of trusting the draft. Returns True when a
    correction was applied. All other validation still applies.
    """
    assessment = draft.get("assessment")
    questions = draft.get("questions")
    if not isinstance(assessment, dict) or not isinstance(questions, list) or not questions:
        return False
    marks = [item.get("max_marks") for item in questions if isinstance(item, dict)]
    if len(marks) != len(questions):
        return False
    if not all(isinstance(mark, (int, float)) and not isinstance(mark, bool) and mark > 0 for mark in marks):
        return False
    total = sum(marks)
    if assessment.get("total_marks") != total:
        assessment["total_marks"] = total
        return True
    return False


async def extract_and_save_blueprint(
    db: Session, assessment: Assessment, content: bytes, filename: str, settings: Settings,
) -> tuple[dict, Blueprint]:
    """Draft a blueprint from a paper PDF with AI, then validate and save it.

    The AI only proposes: each draft goes through parse_blueprint, and its
    validation errors are fed back so the next attempt adapts. After
    MAX_EXTRACTION_ATTEMPTS failures the last error is returned to the teacher.
    save_blueprint then enforces uniqueness, exactly like a JSON upload.
    """
    try:
        paper_text = extract_pdf_text(content)
    except IngestionError:
        paper_text = ""
    provider = get_ai_provider(settings)
    if provider.name == "mock":
        raise RuntimeError(
            "PDF blueprint extraction needs a real AI provider; "
            "AI_PROVIDER=mock cannot read test papers."
        )
    feedback: str | None = None
    last_error: IngestionError | None = None
    for _ in range(MAX_EXTRACTION_ATTEMPTS):
        try:
            draft = await provider.extract_blueprint(
                system_prompt=BLUEPRINT_EXTRACTION_SYSTEM_PROMPT,
                paper_text=paper_text,
                pdf_bytes=content if not paper_text else None,
                filename=filename,
                feedback=feedback,
            )
        except (httpx.HTTPError, RuntimeError) as error:
            raise RuntimeError(f"The AI provider could not read the paper: {error}.") from error
        if not isinstance(draft, dict):
            last_error = IngestionError(
                "The extracted blueprint was not a JSON object.",
                [IngestionIssue(
                    source="blueprint_pdf", code="EXTRACTION_INVALID",
                    message="The AI did not return a blueprint object.",
                    suggested_fix="Try again, or upload the blueprint as JSON.",
                )],
            )
        else:
            _normalize_totals(draft)
            try:
                blueprint = parse_blueprint(json.dumps(draft))
            except IngestionError as error:
                last_error = error
            else:
                save_blueprint(db, assessment, blueprint)
                return assessment_summary(assessment), blueprint
        assert last_error is not None
        feedback = (
            f"Your previous draft failed validation: {_describe(last_error)} "
            "Regenerate the complete corrected blueprint JSON."
        )
    assert last_error is not None
    raise last_error
