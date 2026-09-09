from collections import defaultdict
from typing import Any

from app.schemas.analysis import StudentAnalysis
from app.schemas.blueprint import Blueprint


def build_evidence(
    blueprint: Blueprint,
    analysis: StudentAnalysis,
    *,
    duration_minutes: int = 30,
    question_count: int = 8,
) -> dict[str, Any]:
    concept_context: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"skills": set(), "cognitive": set(), "keywords": set()}
    )
    for question in blueprint.questions:
        concept_context[question.concept]["skills"].add(question.skill)
        concept_context[question.concept]["cognitive"].add(question.cognitive_category)
        concept_context[question.concept]["keywords"].update(question.keywords)

    concepts = []
    for metric in analysis.concepts:
        context = concept_context[metric.name]
        combined = " ".join(context["skills"] | context["cognitive"]).lower()
        reasoning_type = (
            "experimental" if "experiment" in combined else
            "application" if "application" in combined else
            "reasoning" if "reason" in combined else
            "recall" if any(word in combined for word in ("recall", "knowledge")) else "mixed"
        )
        concepts.append({**metric.model_dump(), "reasoning_type": reasoning_type})

    weak = [item for item in concepts if item["classification"] in {"Needs Support", "Developing"}]
    strong = [item for item in concepts if item["classification"] in {"Secure", "Strong"}]
    allowed = [item["name"] for item in weak] or [item["name"] for item in concepts]

    easy = round(question_count * 0.3)
    challenging = round(question_count * 0.2)
    medium = question_count - easy - challenging
    return {
        "student_ref": f"Student {analysis.student_id}",
        "assessment": {
            "title": blueprint.assessment.title,
            "subject": blueprint.assessment.subject,
            "grade": blueprint.assessment.grade,
        },
        "overall": {
            "score": analysis.score,
            "max_score": analysis.max_score,
            "percentage": analysis.percentage,
            "classification": analysis.classification,
        },
        "concepts": concepts,
        "weaknesses": weak,
        "strengths": strong,
        "allowed_concepts": allowed,
        "allowed_question_ids": [question.question_id for question in blueprint.questions],
        "concept_keywords": {
            name: sorted(values["keywords"]) for name, values in concept_context.items()
        },
        "options": {
            "duration_minutes": duration_minutes,
            "question_count": question_count,
            "difficulty_counts": {"easy": easy, "medium": medium, "challenging": challenging},
        },
    }

