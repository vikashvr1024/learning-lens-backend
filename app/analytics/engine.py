from collections import defaultdict
from collections.abc import Callable

from app.core.config import Settings, get_settings
from app.schemas.analysis import CohortAnalysis, Metric, QuestionMetric, StudentAnalysis
from app.schemas.blueprint import Blueprint, QuestionBlueprint


def classify(ratio: float, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if ratio < settings.weak_threshold:
        return "Needs Support"
    if ratio < settings.developing_threshold:
        return "Developing"
    if ratio < settings.strong_threshold:
        return "Secure"
    return "Strong"


def _aggregate(
    questions: list[QuestionBlueprint], scores: dict[str, float], key: Callable[[QuestionBlueprint], str]
) -> list[Metric]:
    buckets: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "ids": []})
    for question in questions:
        name = key(question)
        buckets[name]["score"] += scores[question.question_id]
        buckets[name]["max"] += question.max_marks
        buckets[name]["ids"].append(question.question_id)
    metrics = []
    for name, value in buckets.items():
        ratio = value["score"] / value["max"]
        metrics.append(Metric(
            name=name, score=round(value["score"], 4), max_score=round(value["max"], 4),
            percentage=round(ratio * 100, 2), classification=classify(ratio),
            question_ids=value["ids"],
        ))
    return sorted(metrics, key=lambda metric: metric.name.lower())


def analyze_student(blueprint: Blueprint, record: dict) -> StudentAnalysis:
    scores = record["scores"]
    question_metrics: list[QuestionMetric] = []
    for question in blueprint.questions:
        score = scores[question.question_id]
        ratio = score / question.max_marks
        status = "missed" if score == 0 else "full" if score == question.max_marks else "partial"
        question_metrics.append(QuestionMetric(
            question_id=question.question_id, score=score, max_score=question.max_marks,
            percentage=round(ratio * 100, 2), status=status, topic=question.topic,
            concept=question.concept, skill=question.skill,
            cognitive_category=question.cognitive_category,
        ))
    total = sum(scores.values())
    possible = blueprint.assessment.total_marks
    ratio = total / possible
    topics = _aggregate(blueprint.questions, scores, lambda q: q.topic)
    concepts = _aggregate(blueprint.questions, scores, lambda q: q.concept)
    skills = _aggregate(blueprint.questions, scores, lambda q: q.skill)
    cognitive = _aggregate(blueprint.questions, scores, lambda q: q.cognitive_category)

    def extrema(metrics: list[Metric], weakest: bool) -> list[str]:
        if not metrics:
            return []
        target = (min if weakest else max)(metric.percentage for metric in metrics)
        return [metric.name for metric in metrics if metric.percentage == target]

    return StudentAnalysis(
        student_id=record["student_id"], student_name=record["student_name"],
        score=round(total, 4), max_score=possible, percentage=round(ratio * 100, 2),
        classification=classify(ratio), questions=question_metrics, topics=topics,
        concepts=concepts, skills=skills, cognitive_categories=cognitive,
        strongest_topics=extrema(topics, False), weakest_topics=extrema(topics, True),
        strongest_concepts=extrema(concepts, False), weakest_concepts=extrema(concepts, True),
        strongest_skills=extrema(skills, False), weakest_skills=extrema(skills, True),
        fully_missed_questions=[q.question_id for q in question_metrics if q.status == "missed"],
        partially_correct_questions=[q.question_id for q in question_metrics if q.status == "partial"],
    )


def analyze_cohort(blueprint: Blueprint, students: list[StudentAnalysis]) -> CohortAnalysis:
    if not students:
        return CohortAnalysis(
            student_count=0, class_average=0, question_averages=[], topic_averages=[],
            concept_averages=[], skill_averages=[], cognitive_averages=[],
            score_distribution={label: 0 for label in ("Needs Support", "Developing", "Secure", "Strong")},
            concept_struggle=[],
        )
    synthetic = {
        "student_id": "cohort", "student_name": "Cohort",
        "scores": {
            question.question_id: sum(
                next(metric.score for metric in student.questions if metric.question_id == question.question_id)
                for student in students
            ) / len(students)
            for question in blueprint.questions
        },
    }
    average = analyze_student(blueprint, synthetic)
    distribution = {label: 0 for label in ("Needs Support", "Developing", "Secure", "Strong")}
    for student in students:
        distribution[student.classification] += 1
    concept_struggle = []
    for metric in average.concepts:
        struggling = sum(
            next(item for item in student.concepts if item.name == metric.name).classification
            in {"Needs Support", "Developing"}
            for student in students
        )
        concept_struggle.append({
            "concept": metric.name, "students": struggling,
            "percentage": round(struggling / len(students) * 100, 2),
        })
    return CohortAnalysis(
        student_count=len(students),
        class_average=round(sum(student.percentage for student in students) / len(students), 2),
        question_averages=[Metric(
            name=item.question_id, score=item.score, max_score=item.max_score,
            percentage=item.percentage, classification=classify(item.percentage / 100),
            question_ids=[item.question_id],
        ) for item in average.questions],
        topic_averages=average.topics, concept_averages=average.concepts,
        skill_averages=average.skills, cognitive_averages=average.cognitive_categories,
        score_distribution=distribution, concept_struggle=concept_struggle,
    )

