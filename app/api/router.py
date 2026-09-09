from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import AIGenerationFailed
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.ingestion.blueprint import parse_blueprint
from app.ingestion.errors import IngestionError
from app.models import AIGeneration, Assessment
from app.reports.html import render_student_report, render_worksheet
from app.services.assessments import (
    assessment_summary,
    batch_summary_csv,
    create_assessment,
    delete_assessment,
    get_assessment,
    get_student_assessment,
    import_results,
    list_student_assessments,
    load_demo,
    save_blueprint,
)
from app.services.blueprint_extraction import extract_and_save_blueprint
from app.services.generation import generate_artifact

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(default="Pending blueprint", max_length=100)
    grade: str = Field(default="Pending", max_length=100)


class GenerationOptions(BaseModel):
    force: bool = False
    duration_minutes: int = Field(default=30, ge=10, le=120)
    question_count: int = Field(default=8, ge=3, le=30)


def not_found(kind: str = "Assessment") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"{kind} not found."},
    )


@router.get("/assessments")
def assessments(db: Db):
    records = db.scalars(select(Assessment).order_by(Assessment.created_at.desc())).all()
    return [assessment_summary(item) for item in records]


@router.post("/assessments", status_code=201)
def new_assessment(payload: AssessmentCreate, db: Db):
    return assessment_summary(create_assessment(db, payload.title, payload.subject, payload.grade))


@router.delete("/assessments/{assessment_id}", status_code=204)
def remove_assessment(assessment_id: str, db: Db):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    delete_assessment(db, assessment)
    return Response(status_code=204)


@router.post("/assessments/{assessment_id}/blueprint")
async def upload_blueprint(assessment_id: str, db: Db, file: UploadFile = File(...)):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=415,
            detail={"code": "INVALID_FILE_TYPE", "message": "Blueprint must be a .json file."},
        )
    content = await file.read()
    if len(content) > 2_000_000:
        raise HTTPException(
            status_code=413,
            detail={"code": "FILE_TOO_LARGE", "message": "Blueprint exceeds the 2 MB limit."},
        )
    try:
        blueprint = parse_blueprint(content)
        save_blueprint(db, assessment, blueprint)
    except IngestionError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BLUEPRINT_INVALID", "message": str(error),
                "errors": [item.as_dict() for item in error.issues],
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "ASSESSMENT_CONFLICT", "message": str(error)},
        ) from error
    return {
        "assessment": assessment_summary(assessment),
        "validation": {
            "status": "valid", "question_count": len(blueprint.questions),
            "total_marks": blueprint.assessment.total_marks,
        },
    }


@router.post("/assessments/{assessment_id}/blueprint-pdf")
async def upload_blueprint_pdf(
    assessment_id: str, db: Db, file: UploadFile = File(...),
    results: UploadFile | None = File(None),
    settings: Settings = Depends(get_settings),
):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail={"code": "INVALID_FILE_TYPE", "message": "Paper must be a .pdf file."},
        )
    content = await file.read()
    if len(content) > 10_000_000:
        raise HTTPException(
            status_code=413,
            detail={"code": "FILE_TOO_LARGE", "message": "Paper exceeds the 10 MB limit."},
        )
    results_content: bytes | None = None
    if results is not None and results.filename:
        if not results.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=415,
                detail={"code": "INVALID_FILE_TYPE", "message": "Performance data must be a .csv file."},
            )
        results_content = await results.read()
        if len(results_content) > 5_000_000:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": "Performance file exceeds the 5 MB limit."},
            )
    try:
        summary, blueprint, imported = await extract_and_save_blueprint(
            db, assessment, content, file.filename, settings, results_content,
        )
    except IngestionError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BLUEPRINT_INVALID", "message": str(error),
                "errors": [item.as_dict() for item in error.issues],
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "ASSESSMENT_CONFLICT", "message": str(error)},
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "AI_NOT_CONFIGURED", "message": str(error)},
        ) from error
    payload: dict = {
        "assessment": summary,
        "validation": {
            "status": "valid", "question_count": len(blueprint.questions),
            "total_marks": blueprint.assessment.total_marks,
        },
        "source": "pdf",
    }
    if results_content is not None:
        payload["results"] = {"status": "valid", "row_count": imported}
    return payload


@router.post("/assessments/{assessment_id}/results")
async def upload_results(assessment_id: str, db: Db, file: UploadFile = File(...)):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail={"code": "INVALID_FILE_TYPE", "message": "Performance data must be a .csv file."},
        )
    content = await file.read()
    if len(content) > 5_000_000:
        raise HTTPException(
            status_code=413,
            detail={"code": "FILE_TOO_LARGE", "message": "Performance file exceeds the 5 MB limit."},
        )
    try:
        rows = import_results(db, assessment, content)
    except IngestionError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RESULTS_INVALID", "message": str(error),
                "errors": [item.as_dict() for item in error.issues],
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "IMPORT_CONFLICT", "message": str(error)},
        ) from error
    return {
        "validation": {"status": "valid", "row_count": len(rows)},
        "assessment": assessment_summary(assessment),
    }


@router.get("/assessments/{assessment_id}")
def assessment_detail(assessment_id: str, db: Db):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    return {
        **assessment_summary(assessment),
        "blueprint": assessment.blueprint_json,
        "overview": assessment.aggregate_json,
    }


@router.get("/assessments/{assessment_id}/overview")
def assessment_overview(assessment_id: str, db: Db):
    assessment = get_assessment(db, assessment_id)
    if not assessment:
        raise not_found()
    return assessment.aggregate_json or {"student_count": 0, "class_average": 0}


@router.get("/assessments/{assessment_id}/students")
def assessment_students(assessment_id: str, db: Db):
    if not get_assessment(db, assessment_id):
        raise not_found()
    return [
        {
            "id": item.id, "student_id": item.student.external_student_id,
            "name": item.student.name, "score": item.total_score,
            "percentage": item.percentage, "classification": item.classification,
            "weakest_concepts": item.analysis_json.get("weakest_concepts", []),
            "concept_performance": {
                metric["name"]: metric["percentage"]
                for metric in item.analysis_json.get("concepts", [])
            },
        }
        for item in list_student_assessments(db, assessment_id)
    ]


@router.get("/students/{student_assessment_id}")
def student_detail(student_assessment_id: str, db: Db):
    item = get_student_assessment(db, student_assessment_id)
    if not item:
        raise not_found("Student assessment")
    artifacts = db.scalars(
        select(AIGeneration)
        .where(AIGeneration.student_assessment_id == item.id)
        .order_by(AIGeneration.created_at.desc())
    ).all()
    latest: dict[str, dict] = {}
    for artifact in artifacts:
        latest.setdefault(artifact.generation_type, artifact.structured_output)
    return {
        "id": item.id,
        "student": {"id": item.student.external_student_id, "name": item.student.name},
        "assessment": {
            "id": item.assessment.id, "title": item.assessment.title,
            "subject": item.assessment.subject, "grade": item.assessment.grade,
        },
        "analysis": item.analysis_json,
        "artifacts": latest,
    }


@router.post("/students/{student_assessment_id}/analyze")
def analyze(student_assessment_id: str, db: Db):
    item = get_student_assessment(db, student_assessment_id)
    if not item:
        raise not_found("Student assessment")
    return {"analysis": item.analysis_json, "source": "deterministic", "recalculated": False}


async def _generate(
    student_assessment_id: str,
    kind: str,
    options: GenerationOptions,
    db: Session,
):
    item = get_student_assessment(db, student_assessment_id)
    if not item:
        raise not_found("Student assessment")
    try:
        return await generate_artifact(
            db, item, kind, get_settings(), force=options.force,
            duration_minutes=options.duration_minutes,
            question_count=options.question_count,
        )
    except AIGenerationFailed as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "AI_OUTPUT_INVALID", "message": str(error)},
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "AI_NOT_CONFIGURED", "message": str(error)},
        ) from error


@router.post("/students/{student_assessment_id}/generate-diagnosis")
async def generate_diagnosis(student_assessment_id: str, options: GenerationOptions, db: Db):
    return await _generate(student_assessment_id, "diagnosis", options, db)


@router.post("/students/{student_assessment_id}/generate-recommendations")
async def generate_recommendations(student_assessment_id: str, options: GenerationOptions, db: Db):
    return await _generate(student_assessment_id, "recommendations", options, db)


@router.post("/students/{student_assessment_id}/generate-lesson-plan")
async def generate_lesson_plan(student_assessment_id: str, options: GenerationOptions, db: Db):
    return await _generate(student_assessment_id, "lesson_plan", options, db)


@router.post("/students/{student_assessment_id}/generate-worksheet")
async def generate_worksheet(student_assessment_id: str, options: GenerationOptions, db: Db):
    return await _generate(student_assessment_id, "worksheet", options, db)


@router.get("/students/{student_assessment_id}/report", response_class=HTMLResponse)
def student_report(student_assessment_id: str, db: Db):
    item = get_student_assessment(db, student_assessment_id)
    if not item:
        raise not_found("Student assessment")
    return render_student_report(db, item)


@router.get("/students/{student_assessment_id}/worksheet", response_class=HTMLResponse)
def worksheet_report(student_assessment_id: str, db: Db):
    item = get_student_assessment(db, student_assessment_id)
    if not item:
        raise not_found("Student assessment")
    return render_worksheet(db, item)


@router.get("/assessments/{assessment_id}/summary.csv", response_class=PlainTextResponse)
def download_summary(assessment_id: str, db: Db):
    if not get_assessment(db, assessment_id):
        raise not_found()
    return PlainTextResponse(
        batch_summary_csv(db, assessment_id), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=batch-diagnostic-summary.csv"},
    )


@router.post("/demo/load")
def seed_demo(db: Db, settings: Settings = Depends(get_settings)):
    if not settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail={"code": "DEMO_DISABLED", "message": "Demo mode is disabled."},
        )
    assessment = load_demo(db, Path(__file__).resolve().parents[2])
    return assessment_summary(assessment)


@router.get("/settings/status")
def settings_status(settings: Settings = Depends(get_settings)):
    return {
        "demo_mode": settings.demo_mode, "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model, "api_key_configured": bool(settings.ai_api_key),
    }
