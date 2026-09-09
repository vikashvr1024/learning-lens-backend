from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssessmentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    grade: str = Field(min_length=1, max_length=100)
    school: str | None = Field(default=None, max_length=200)
    total_marks: float = Field(gt=0)
    language: str = Field(default="English", min_length=1, max_length=50)
    extensions: dict[str, Any] = Field(default_factory=dict)


class QuestionBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    question_number: int | str
    max_marks: float = Field(gt=0)
    topic: str = Field(min_length=1, max_length=150)
    concept: str = Field(min_length=1, max_length=150)
    subconcept: str | None = Field(default=None, max_length=200)
    skill: str = Field(default="Unspecified", min_length=1, max_length=150)
    cognitive_category: str = Field(default="Unspecified", min_length=1, max_length=150)
    difficulty: str | None = Field(default=None, max_length=50)
    learning_objectives: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class Blueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: AssessmentInfo
    questions: list[QuestionBlueprint] = Field(min_length=1)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_questions_and_marks(self) -> "Blueprint":
        ids = [question.question_id for question in self.questions]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"Blueprint contains duplicate question ID {duplicates[0]}.")
        calculated_total = sum(question.max_marks for question in self.questions)
        if abs(calculated_total - self.assessment.total_marks) > 1e-9:
            raise ValueError(
                f"Assessment total_marks is {self.assessment.total_marks:g}, but question marks "
                f"sum to {calculated_total:g}."
            )
        return self

