from app.ai.schemas import Diagnosis, LessonPlan, Recommendations, WorksheetOutput


class AIOutputValidationError(ValueError):
    pass


def validate_grounding(output, evidence: dict) -> None:
    allowed = set(evidence["allowed_concepts"])
    used: list[str] = []
    if isinstance(output, Diagnosis):
        all_used = [item.concept for item in output.strengths + output.learning_gaps]
        used = [item.concept for item in output.learning_gaps]
        all_blueprint_concepts = {item["name"] for item in evidence["concepts"]}
        if not set(all_used).issubset(all_blueprint_concepts):
            raise AIOutputValidationError("Diagnosis used concepts outside the supplied blueprint.")
    elif isinstance(output, Recommendations):
        used = [item.concept for item in output.recommendations]
    elif isinstance(output, LessonPlan):
        used = output.target_concepts
        if output.duration_minutes != evidence["options"]["duration_minutes"]:
            raise AIOutputValidationError("Lesson duration did not match the teacher's request.")
        segment_total = sum([
            output.warm_up.minutes, output.explicit_instruction.minutes,
            output.guided_practice.minutes, output.independent_practice.minutes,
            output.assessment_check.minutes,
        ])
        if segment_total != output.duration_minutes:
            raise AIOutputValidationError("Lesson segment minutes do not add up to the duration.")
    elif isinstance(output, WorksheetOutput):
        used = output.target_concepts + [item.concept for item in output.questions]
        expected = evidence["options"]["question_count"]
        if len(output.questions) != expected:
            raise AIOutputValidationError(f"Worksheet contains {len(output.questions)} questions; expected {expected}.")
        if len({item.id for item in output.questions}) != len(output.questions):
            raise AIOutputValidationError("Worksheet question IDs must be unique.")
        actual_difficulties = {level: 0 for level in ("easy", "medium", "challenging")}
        for item in output.questions:
            actual_difficulties[item.difficulty] += 1
        if actual_difficulties != evidence["options"]["difficulty_counts"]:
            raise AIOutputValidationError("Worksheet difficulty distribution did not match the request.")
    if not set(used).issubset(allowed):
        unknown = sorted(set(used) - allowed)
        raise AIOutputValidationError(
            f"AI used concepts outside the allowed remediation set: {', '.join(unknown)}."
        )
