from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIGeneration, StudentAssessment

FOREST = colors.HexColor("#176B52")
INK = colors.HexColor("#17221B")
MUTED = colors.HexColor("#64748B")
MINT = colors.HexColor("#E8F5EF")
LINE = colors.HexColor("#DCE7E1")
CANVAS = colors.HexColor("#F7FAF8")


def _fonts() -> tuple[str, str]:
    candidates = [
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("LearningLens", str(regular)))
            pdfmetrics.registerFont(TTFont("LearningLens-Bold", str(bold)))
            return "LearningLens", "LearningLens-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _fonts()


def _text(value: Any) -> str:
    cleaned = str(value or "").translate(
        str.maketrans({
            "\u2011": "-", "\u2013": "-", "\u2014": "-",
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        })
    )
    return escape(cleaned).replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=sample["Title"], fontName=FONT_BOLD, fontSize=24,
            leading=29, textColor=INK, alignment=TA_CENTER, spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=sample["Normal"], fontName=FONT, fontSize=10,
            leading=15, textColor=MUTED, alignment=TA_CENTER, spaceAfter=18,
        ),
        "section": ParagraphStyle(
            "Section", parent=sample["Heading2"], fontName=FONT_BOLD, fontSize=15,
            leading=19, textColor=FOREST, spaceBefore=13, spaceAfter=8,
        ),
        "heading": ParagraphStyle(
            "Heading", parent=sample["Heading3"], fontName=FONT_BOLD, fontSize=11,
            leading=15, textColor=INK, spaceBefore=7, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=sample["BodyText"], fontName=FONT, fontSize=9.5,
            leading=14, textColor=INK, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small", parent=sample["BodyText"], fontName=FONT, fontSize=8,
            leading=11, textColor=MUTED, spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "Label", parent=sample["BodyText"], fontName=FONT_BOLD, fontSize=8,
            leading=10, textColor=FOREST, spaceAfter=2,
        ),
    }


def _latest_artifacts(db: Session, item: StudentAssessment) -> dict[str, dict[str, Any]]:
    artifacts = db.scalars(
        select(AIGeneration)
        .where(AIGeneration.student_assessment_id == item.id)
        .order_by(AIGeneration.created_at.desc())
    ).all()
    latest: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        latest.setdefault(artifact.generation_type, artifact.structured_output)
    return latest


def _bullet_list(items: list[Any], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(_text(item), styles["body"]), leftIndent=12) for item in items],
        bulletType="bullet", start="circle", leftIndent=16, bulletFontName=FONT,
        bulletFontSize=6, bulletColor=FOREST, spaceAfter=6,
    )


def _number_list(items: list[Any], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(_text(item), styles["body"]), leftIndent=15) for item in items],
        bulletType="1", leftIndent=20, bulletFontName=FONT_BOLD,
        bulletFontSize=8, bulletColor=FOREST, spaceAfter=6,
    )


def _build_pdf(title: str, story: list[Any]) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=18 * mm, bottomMargin=17 * mm, title=title, author="Learning Lens",
    )

    def decorate_page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(17 * mm, 13 * mm, A4[0] - 17 * mm, 13 * mm)
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 8.5 * mm, "Learning Lens")
        canvas.drawRightString(A4[0] - 17 * mm, 8.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return output.getvalue()


def render_student_report_pdf(db: Session, item: StudentAssessment) -> bytes:
    styles = _styles()
    artifacts = _latest_artifacts(db, item)
    analysis = item.analysis_json
    diagnosis = artifacts.get("diagnosis", {})
    recommendations = artifacts.get("recommendations", {}).get("recommendations", [])
    lesson = artifacts.get("lesson_plan", {})

    story: list[Any] = [
        Paragraph("Independent Exam Guide", styles["title"]),
        Paragraph(
            f"{_text(item.student.name)} | {_text(item.assessment.title)}",
            styles["subtitle"],
        ),
    ]
    overview = Table(
        [[
            Paragraph(f"<b>{analysis['score']:g} / {analysis['max_score']:g}</b><br/>Score", styles["body"]),
            Paragraph(f"<b>{analysis['percentage']:g}%</b><br/>Percentage", styles["body"]),
            Paragraph(f"<b>{_text(analysis['classification'])}</b><br/>Current progress", styles["body"]),
        ]],
        colWidths=[document_width / 3 for document_width in [A4[0] - 34 * mm] * 3],
    )
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([overview, Spacer(1, 8)])

    story.append(Paragraph("What your results mean", styles["section"]))
    story.append(Paragraph(
        _text(diagnosis.get("summary", "Generate support to add your personalized explanation.")),
        styles["body"],
    ))

    gaps = diagnosis.get("learning_gaps", [])
    if gaps:
        story.append(Paragraph("What to revise first", styles["section"]))
        for gap in gaps:
            story.extend([
                Paragraph(_text(gap.get("concept")), styles["heading"]),
                Paragraph(_text(gap.get("explanation")), styles["body"]),
                Paragraph(f"Based on: {_text(gap.get('evidence'))}", styles["small"]),
            ])
    else:
        priorities = analysis.get("weakest_concepts", [])
        if priorities:
            story.extend([
                Paragraph("What to revise first", styles["section"]),
                _bullet_list(priorities, styles),
            ])

    next_steps = diagnosis.get("teacher_focus", [])
    if next_steps:
        story.extend([
            Paragraph("Your next study steps", styles["section"]),
            _number_list(next_steps, styles),
        ])

    if recommendations:
        story.append(Paragraph("Learn each priority", styles["section"]))
        for index, recommendation in enumerate(recommendations, start=1):
            block = [
                Paragraph(
                    f"{index}. {_text(recommendation.get('concept'))}", styles["heading"]
                ),
                Paragraph("LEARN IT THIS WAY", styles["label"]),
                Paragraph(_text(recommendation.get("teaching_approach")), styles["body"]),
                Paragraph("TRY THIS NOW", styles["label"]),
                Paragraph(_text(recommendation.get("mini_activity")), styles["body"]),
                Paragraph("COMMON EXAM MISTAKE", styles["label"]),
                Paragraph(_text(recommendation.get("misconception_to_watch")), styles["body"]),
                Paragraph("CHECK YOURSELF", styles["label"]),
                Paragraph(_text(recommendation.get("follow_up_check")), styles["body"]),
                HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=4, spaceAfter=5),
            ]
            story.append(KeepTogether(block))

    if lesson:
        story.extend([
            PageBreak(),
            Paragraph("Your self-study plan", styles["section"]),
            Paragraph(
                f"{_text(lesson.get('title'))} - {lesson.get('duration_minutes', 0)} minutes",
                styles["heading"],
            ),
        ])
        segments = [
            ("Get ready", lesson.get("warm_up", {})),
            ("Learn", lesson.get("explicit_instruction", {})),
            ("Practise with guidance", lesson.get("guided_practice", {})),
            ("Try it yourself", lesson.get("independent_practice", {})),
            ("Mark your progress", lesson.get("assessment_check", {})),
        ]
        rows = [["Step", "Time", "What to do"]]
        for label, segment in segments:
            rows.append([
                Paragraph(_text(label), styles["body"]),
                Paragraph(f"{segment.get('minutes', 0)} min", styles["body"]),
                Paragraph(_text(segment.get("activity")), styles["body"]),
            ])
        plan = Table(rows, colWidths=[34 * mm, 18 * mm, A4[0] - 86 * mm], repeatRows=1)
        plan.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FOREST),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CANVAS]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(plan)

    return _build_pdf(f"{item.student.name} - Independent Exam Guide", story)


def render_worksheet_pdf(db: Session, item: StudentAssessment) -> bytes:
    styles = _styles()
    content = _latest_artifacts(db, item).get("worksheet")
    if not content:
        return _build_pdf(
            "Worksheet not generated",
            [
                Paragraph("Worksheet not generated", styles["title"]),
                Paragraph(
                    "Generate support from the student screen, then open the worksheet again.",
                    styles["body"],
                ),
            ],
        )

    story: list[Any] = [
        Paragraph(_text(content.get("title")), styles["title"]),
        Paragraph(
            f"{_text(item.student.name)} | {_text(item.assessment.title)}",
            styles["subtitle"],
        ),
        Paragraph(_text(content.get("instructions")), styles["body"]),
        Spacer(1, 6),
    ]
    for question in content.get("questions", []):
        block: list[Any] = [
            Paragraph(
                f"{_text(question.get('id'))}. {_text(question.get('question'))}",
                styles["heading"],
            ),
            Paragraph(
                f"{_text(question.get('difficulty', '')).title()} | "
                f"{_text(question.get('type', '')).replace('_', ' ').title()}",
                styles["small"],
            ),
        ]
        options = question.get("options", [])
        if options:
            labelled = [f"{chr(65 + index)}. {option}" for index, option in enumerate(options)]
            block.append(_bullet_list(labelled, styles))
        block.extend([
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=0.45, color=LINE, spaceAfter=12),
            HRFlowable(width="100%", thickness=0.45, color=LINE, spaceAfter=12),
            Spacer(1, 5),
        ])
        story.append(KeepTogether(block))

    story.extend([PageBreak(), Paragraph("Guided solutions", styles["title"])])
    for question in content.get("questions", []):
        solution_steps = question.get("solution_steps", [])
        block = [
            Paragraph(
                f"{_text(question.get('id'))}. Step-by-step solution",
                styles["heading"],
            ),
        ]
        if solution_steps:
            block.append(_number_list(solution_steps, styles))
        else:
            block.append(Paragraph(
                "Regenerate support to add the new guided solution.", styles["body"]
            ))
        block.extend([
            Paragraph("FINAL ANSWER", styles["label"]),
            Paragraph(_text(question.get("answer")), styles["body"]),
        ])
        if question.get("exam_tip"):
            block.extend([
                Paragraph("EXAM TIP", styles["label"]),
                Paragraph(_text(question.get("exam_tip")), styles["body"]),
            ])
        block.extend([
            Paragraph("HOW MARKS ARE EARNED", styles["label"]),
            Paragraph(_text(question.get("marking_notes")), styles["body"]),
            HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=3, spaceAfter=8),
        ])
        story.append(KeepTogether(block))

    return _build_pdf(f"{item.student.name} - Practice Worksheet", story)
