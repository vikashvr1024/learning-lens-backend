from pathlib import Path

from app.analytics.engine import analyze_cohort, analyze_student
from app.ingestion.blueprint import parse_blueprint
from app.ingestion.csv_results import parse_results_csv

ROOT = Path(__file__).resolve().parents[2]


def test_deterministic_student_and_cohort_analytics():
    blueprint = parse_blueprint((ROOT / "examples" / "p4_light_blueprint.json").read_bytes())
    records = parse_results_csv((ROOT / "examples" / "p4_light_results.csv").read_bytes(), blueprint)
    students = [analyze_student(blueprint, row) for row in records]
    arun = students[0]
    assert arun.score == 10
    assert arun.percentage == 50
    assert arun.classification == "Developing"
    assert "Experimental Skills" in arun.weakest_skills
    assert "Q3" in arun.partially_correct_questions
    cohort = analyze_cohort(blueprint, students)
    assert cohort.student_count == 4
    assert cohort.class_average == 62.5
    assert len(cohort.topic_averages) == 2
    assert any(metric.name == "Application" for metric in cohort.skill_averages)
