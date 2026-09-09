import json

import httpx
from sqlalchemy.orm import Session

from app.ai.factory import get_ai_provider
from app.core.config import Settings
from app.ingestion.blueprint import parse_blueprint
from app.ingestion.csv_results import result_question_ids
from app.ingestion.errors import IngestionError, IngestionIssue
from app.ingestion.pdf_text import extract_pdf_text
from app.models import Assessment
from app.prompts.blueprint_extraction import BLUEPRINT_EXTRACTION_SYSTEM_PROMPT
from app.schemas.blueprint import Blueprint
from app.services.assessments import assessment_summary, import_results, save_blueprint

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


def _check_required_ids(blueprint: Blueprint, required_ids: list[str]) -> IngestionError | None:
    """Ensure the draft covers exactly the teacher's scored questions."""
    have = {question.question_id for question in blueprint.questions}
    want = set(required_ids)
    missing = sorted(want - have)
    extra = sorted(have - want)
    if not missing and not extra:
        return None
    parts = []
    if missing:
        parts.append(f"missing {', '.join(missing)}")
    if extra:
        parts.append(f"unexpected {', '.join(extra)}")
    return IngestionError(
        f"Extracted blueprint does not cover the scored questions ({'; '.join(parts)}).",
        [IngestionIssue(
            source="blueprint_pdf", code="EXTRACTION_INCOMPLETE",
            message=f"Question coverage mismatch: {'; '.join(parts)}.",
            suggested_fix="The paper was re-read automatically; if this persists, upload the blueprint as JSON.",
        )],
    )


async def extract_and_save_blueprint(
    db: Session, assessment: Assessment, content: bytes, filename: str, settings: Settings,
    results_content: bytes | None = None,
) -> tuple[dict, Blueprint, int]:
    """Draft a blueprint from a paper PDF with AI, then validate and save it.

    When the teacher's scores CSV is supplied, its columns define the exact
    question inventory the draft must cover, and matching results are imported
    in the same call. The AI only proposes: parse_blueprint enforces the schema
    and mark totals, the required-ID check enforces coverage, and
    save_blueprint enforces uniqueness, exactly like a JSON upload. Scores are
    never modified: out-of-range marks still fail loudly.
    """
    required_ids = result_question_ids(results_content) if results_content else None
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
                required_ids=required_ids,
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
                if required_ids:
                    coverage_error = _check_required_ids(blueprint, required_ids)
                    if coverage_error is not None:
                        raise coverage_error
            except IngestionError as error:
                last_error = error
            else:
                save_blueprint(db, assessment, blueprint)
                imported = 0
                if results_content:
                    imported = len(import_results(db, assessment, results_content))
                return assessment_summary(assessment), blueprint, imported
        assert last_error is not None
        feedback = (
            f"Your previous draft failed validation: {_describe(last_error)} "
            "Regenerate the complete corrected blueprint JSON."
        )
    assert last_error is not None
    raise last_error
