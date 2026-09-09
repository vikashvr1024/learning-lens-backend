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


async def extract_and_save_blueprint(
    db: Session, assessment: Assessment, content: bytes, filename: str, settings: Settings,
) -> tuple[dict, Blueprint]:
    """Draft a blueprint from a paper PDF with AI, then validate and save it.

    The AI only proposes: parse_blueprint enforces the schema and mark totals,
    and save_blueprint enforces uniqueness, exactly like a JSON upload.
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
    try:
        draft = await provider.extract_blueprint(
            system_prompt=BLUEPRINT_EXTRACTION_SYSTEM_PROMPT,
            paper_text=paper_text,
            pdf_bytes=content if not paper_text else None,
            filename=filename,
        )
    except (httpx.HTTPError, RuntimeError) as error:
        raise RuntimeError(f"The AI provider could not read the paper: {error}.") from error
    if not isinstance(draft, dict):
        raise IngestionError(
            "The extracted blueprint was not a JSON object.",
            [IngestionIssue(
                source="blueprint_pdf", code="EXTRACTION_INVALID",
                message="The AI did not return a blueprint object.",
                suggested_fix="Try again, or upload the blueprint as JSON.",
            )],
        )
    blueprint = parse_blueprint(json.dumps(draft))
    save_blueprint(db, assessment, blueprint)
    return assessment_summary(assessment), blueprint
