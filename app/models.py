from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(100), default="Pending blueprint")
    grade: Mapped[str] = mapped_column(String(100), default="Pending")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    blueprint_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    aggregate_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    questions: Mapped[list["Question"]] = relationship(cascade="all, delete-orphan")
    student_assessments: Mapped[list["StudentAssessment"]] = relationship(cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("assessment_id", "question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(80))
    question_number: Mapped[str] = mapped_column(String(30))
    max_marks: Mapped[float] = mapped_column(Float)
    topic: Mapped[str] = mapped_column(String(150))
    concept: Mapped[str] = mapped_column(String(150))
    skill: Mapped[str] = mapped_column(String(150))
    cognitive_category: Mapped[str] = mapped_column(String(150))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_student_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudentAssessment(Base):
    __tablename__ = "student_assessments"
    __table_args__ = (UniqueConstraint("student_id", "assessment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    total_score: Mapped[float] = mapped_column(Float)
    percentage: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(30))
    analysis_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped[Student] = relationship()
    assessment: Mapped[Assessment] = relationship(back_populates="student_assessments")
    scores: Mapped[list["QuestionScore"]] = relationship(cascade="all, delete-orphan")
    generations: Mapped[list["AIGeneration"]] = relationship(cascade="all, delete-orphan")
    worksheets: Mapped[list["Worksheet"]] = relationship(cascade="all, delete-orphan")


class QuestionScore(Base):
    __tablename__ = "question_scores"
    __table_args__ = (UniqueConstraint("student_assessment_id", "question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("student_assessments.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(80))
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("student_assessments.id", ondelete="CASCADE"), index=True
    )
    generation_type: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON)
    validation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Worksheet(Base):
    __tablename__ = "worksheets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("student_assessments.id", ondelete="CASCADE"), index=True
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
