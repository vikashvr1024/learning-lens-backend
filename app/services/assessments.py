import csv
import io
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.analytics.engine import analyze_cohort, analyze_student
from app.ingestion.blueprint import parse_blueprint
from app.ingestion.csv_results import parse_results_csv
from app.models import Assessment, Question, QuestionScore, Student, StudentAssessment
from app.schemas.blueprint import Blueprint


def create_assessment(db: Session, title: str, subject: str = "Pending blueprint", grade: str = "Pending") -> Assessment:
    assessment = Assessment(title=title, subject=subject, grade=grade)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def get_assessment(db: Session, assessment_id: str) -> Assessment | None:
    return db.scalar(select(Assessment).where(Assessment.id == assessment_id))


def delete_assessment(db: Session, assessment: Assessment) -> None:
    """Delete an assessment and every result or generated artifact owned by it."""
    db.delete(assessment)
    db.commit()


def save_blueprint(db: Session, assessment: Assessment, blueprint: Blueprint) -> Assessment:
    existing = db.scalar(
        select(Assessment).where(
            Assessment.external_id == blueprint.assessment.id,
            Assessment.id != assessment.id,
        )
    )
    if existing:
        raise ValueError(f"An assessment with blueprint ID {blueprint.assessment.id} already exists.")
    db.execute(delete(Question).where(Question.assessment_id == assessment.id))
    assessment.external_id = blueprint.assessment.id
    assessment.title = blueprint.assessment.title
    assessment.subject = blueprint.assessment.subject
    assessment.grade = blueprint.assessment.grade
    assessment.blueprint_json = blueprint.model_dump(mode="json")
    assessment.status = "blueprint_ready"
    for question in blueprint.questions:
        db.add(Question(
            assessment_id=assessment.id, question_id=question.question_id,
            question_number=str(question.question_number), max_marks=question.max_marks,
            topic=question.topic, concept=question.concept, skill=question.skill,
            cognitive_category=question.cognitive_category,
            metadata_json={
                "subconcept": question.subconcept, "difficulty": question.difficulty,
                "learning_objectives": question.learning_objectives,
                "keywords": question.keywords, "extensions": question.extensions,
            },
        ))
    db.commit()
    db.refresh(assessment)
    return assessment


def import_results(db: Session, assessment: Assessment, content: bytes) -> list[StudentAssessment]:
    if not assessment.blueprint_json:
        raise ValueError("Upload a valid blueprint before student results.")
    blueprint = Blueprint.model_validate(assessment.blueprint_json)
    records = parse_results_csv(content, blueprint)
    created: list[StudentAssessment] = []
    try:
        for record in records:
            student = db.scalar(
                select(Student).where(Student.external_student_id == record["student_id"])
            )
            if not student:
                student = Student(
                    external_student_id=record["student_id"], name=record["student_name"]
                )
                db.add(student)
                db.flush()
            else:
                student.name = record["student_name"]
            prior = db.scalar(select(StudentAssessment).where(
                StudentAssessment.student_id == student.id,
                StudentAssessment.assessment_id == assessment.id,
            ))
            if prior:
                db.delete(prior)
                db.flush()
            analysis = analyze_student(blueprint, record)
            student_assessment = StudentAssessment(
                student_id=student.id, assessment_id=assessment.id,
                total_score=analysis.score, percentage=analysis.percentage,
                classification=analysis.classification,
                analysis_json=analysis.model_dump(mode="json"),
            )
            db.add(student_assessment)
            db.flush()
            for metric in analysis.questions:
                db.add(QuestionScore(
                    student_assessment_id=student_assessment.id,
                    question_id=metric.question_id, score=metric.score,
                    max_score=metric.max_score,
                ))
            created.append(student_assessment)
        assessment.status = "ready"
        assessment.aggregate_json = analyze_cohort(
            blueprint,
            [analyze_student(blueprint, record) for record in records],
        ).model_dump(mode="json")
        db.commit()
        for item in created:
            db.refresh(item)
        return created
    except Exception:
        db.rollback()
        raise


def assessment_summary(assessment: Assessment) -> dict[str, Any]:
    aggregate = assessment.aggregate_json or {}
    return {
        "id": assessment.id, "external_id": assessment.external_id,
        "title": assessment.title, "subject": assessment.subject, "grade": assessment.grade,
        "status": assessment.status, "question_count": len((assessment.blueprint_json or {}).get("questions", [])),
        "student_count": aggregate.get("student_count", 0),
        "class_average": aggregate.get("class_average", 0),
        "created_at": assessment.created_at.isoformat(),
    }


def list_student_assessments(db: Session, assessment_id: str) -> list[StudentAssessment]:
    return list(db.scalars(
        select(StudentAssessment)
        .options(selectinload(StudentAssessment.student))
        .join(Student)
        .where(StudentAssessment.assessment_id == assessment_id)
        .order_by(Student.name)
    ).all())


def get_student_assessment(db: Session, item_id: str) -> StudentAssessment | None:
    return db.scalar(
        select(StudentAssessment)
        .options(
            selectinload(StudentAssessment.student),
            selectinload(StudentAssessment.assessment),
            selectinload(StudentAssessment.scores),
        )
        .where(StudentAssessment.id == item_id)
    )


def load_demo(db: Session, root: Path) -> Assessment:
    existing = db.scalar(select(Assessment).where(Assessment.external_id == "p4-light-wa3"))
    if existing and existing.status == "ready":
        return existing
    example_dir = root / "examples"
    blueprint = parse_blueprint((example_dir / "p4_light_blueprint.json").read_bytes())
    assessment = existing or create_assessment(db, blueprint.assessment.title)
    save_blueprint(db, assessment, blueprint)
    import_results(db, assessment, (example_dir / "p4_light_results.csv").read_bytes())
    return assessment


def batch_summary_csv(db: Session, assessment_id: str) -> str:
    rows = list_student_assessments(db, assessment_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_id", "student_name", "score", "percentage", "classification", "weakest_concepts"])
    for item in rows:
        writer.writerow([
            item.student.external_student_id, item.student.name, item.total_score,
            item.percentage, item.classification,
            "; ".join(item.analysis_json.get("weakest_concepts", [])),
        ])
    return output.getvalue()
