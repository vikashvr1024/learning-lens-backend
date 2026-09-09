from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiagnosisStrength(StrictModel):
    concept: str
    evidence: str


class LearningGap(StrictModel):
    concept: str
    severity: Literal["low", "medium", "high"]
    reasoning_type: Literal["recall", "application", "experimental", "reasoning", "mixed"]
    evidence: str
    explanation: str


class Diagnosis(StrictModel):
    summary: str
    strengths: list[DiagnosisStrength]
    learning_gaps: list[LearningGap]
    encouragement: str
    teacher_focus: list[str]


class Recommendation(StrictModel):
    concept: str
    priority: Literal["high", "medium", "low"]
    why: str
    teaching_approach: str
    mini_activity: str
    misconception_to_watch: str
    follow_up_check: str


class Recommendations(StrictModel):
    recommendations: list[Recommendation]


class LessonSegment(StrictModel):
    minutes: int = Field(ge=1, le=120)
    activity: str


class LessonPlan(StrictModel):
    title: str
    target_concepts: list[str]
    duration_minutes: int = Field(ge=10, le=120)
    objectives: list[str]
    materials: list[str]
    warm_up: LessonSegment
    explicit_instruction: LessonSegment
    guided_practice: LessonSegment
    independent_practice: LessonSegment
    assessment_check: LessonSegment
    teacher_notes: list[str]


WorksheetType = Literal[
    "multiple_choice", "fill_blank", "true_false", "short_answer",
    "structured_response", "scenario_application",
]


class WorksheetQuestion(StrictModel):
    id: str
    type: WorksheetType
    concept: str
    difficulty: Literal["easy", "medium", "challenging"]
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str
    marking_notes: str
    keywords: list[str] = Field(default_factory=list)


class WorksheetOutput(StrictModel):
    title: str
    student_name: str
    target_concepts: list[str]
    instructions: str
    questions: list[WorksheetQuestion]

