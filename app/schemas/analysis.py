from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Classification = Literal["Needs Support", "Developing", "Secure", "Strong"]


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    score: float
    max_score: float
    percentage: float
    classification: Classification
    question_ids: list[str] = Field(default_factory=list)


class QuestionMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    score: float
    max_score: float
    percentage: float
    status: Literal["missed", "partial", "full"]
    topic: str
    concept: str
    skill: str
    cognitive_category: str


class StudentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str
    student_name: str
    score: float
    max_score: float
    percentage: float
    classification: Classification
    questions: list[QuestionMetric]
    topics: list[Metric]
    concepts: list[Metric]
    skills: list[Metric]
    cognitive_categories: list[Metric]
    strongest_topics: list[str]
    weakest_topics: list[str]
    strongest_concepts: list[str]
    weakest_concepts: list[str]
    strongest_skills: list[str]
    weakest_skills: list[str]
    fully_missed_questions: list[str]
    partially_correct_questions: list[str]


class CohortAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_count: int
    class_average: float
    question_averages: list[Metric]
    topic_averages: list[Metric]
    concept_averages: list[Metric]
    skill_averages: list[Metric]
    cognitive_averages: list[Metric]
    score_distribution: dict[str, int]
    concept_struggle: list[dict]

