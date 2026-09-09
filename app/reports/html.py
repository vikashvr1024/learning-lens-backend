from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIGeneration, StudentAssessment


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;max-width:820px;margin:40px auto;color:#17221b;line-height:1.5}}
h1,h2{{color:#174f3a}} .card{{border:1px solid #dbe5df;border-radius:12px;padding:18px;margin:14px 0}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
@media print{{button{{display:none}}body{{margin:0}}}}</style></head><body><button onclick='print()'>Print / Save PDF</button>{body}</body></html>"""


def render_student_report(db: Session, item: StudentAssessment) -> str:
    artifacts = db.scalars(
        select(AIGeneration).where(AIGeneration.student_assessment_id == item.id)
    ).all()
    by_type = {artifact.generation_type: artifact.structured_output for artifact in artifacts}
    analysis = item.analysis_json
    gaps = "".join(
        f"<li>{escape(name)}</li>" for name in analysis.get("weakest_concepts", [])
    )
    diagnosis = by_type.get("diagnosis", {})
    summary = escape(diagnosis.get("summary", "AI diagnosis has not been generated."))
    body = (
        f"<h1>{escape(item.student.name)} — diagnostic report</h1>"
        f"<p>{escape(item.assessment.title)}</p>"
        f"<div class='card'><h2>Overview</h2><p>{analysis['score']:g} / "
        f"{analysis['max_score']:g} · {analysis['percentage']:g}% · "
        f"{escape(analysis['classification'])}</p></div>"
        f"<div class='card'><h2>Priority concepts</h2><ul>{gaps}</ul></div>"
        f"<div class='card'><h2>Teaching summary</h2><p>{summary}</p></div>"
    )
    return _page(f"{item.student.name} report", body)


def render_worksheet(db: Session, item: StudentAssessment) -> str:
    artifact = db.scalar(
        select(AIGeneration).where(
            AIGeneration.student_assessment_id == item.id,
            AIGeneration.generation_type == "worksheet",
        ).order_by(AIGeneration.created_at.desc())
    )
    if not artifact:
        return _page(
            "Worksheet not generated",
            "<h1>Worksheet not generated</h1><p>Generate it from the student screen first.</p>",
        )
    content = artifact.structured_output
    questions = "".join(
        f"<div class='card'><strong>{escape(q['id'])}. {escape(q['question'])}</strong>"
        "<p>________________________________________</p></div>"
        for q in content["questions"]
    )
    key = "".join(
        f"<tr><td>{escape(q['id'])}</td><td>{escape(q['answer'])}</td></tr>"
        for q in content["questions"]
    )
    body = (
        f"<h1>{escape(content['title'])}</h1><p>{escape(content['instructions'])}</p>"
        f"{questions}<div style='page-break-before:always'><h2>Answer key</h2>"
        f"<table>{key}</table></div>"
    )
    return _page(content["title"], body)

