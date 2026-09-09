from pathlib import Path

import pytest

from app.ingestion.blueprint import parse_blueprint
from app.ingestion.csv_results import parse_results_csv
from app.ingestion.errors import IngestionError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def blueprint():
    return parse_blueprint((ROOT / "examples" / "p4_light_blueprint.json").read_bytes())


def test_valid_csv_normalizes_numbers(blueprint):
    rows = parse_results_csv((ROOT / "examples" / "p4_light_results.csv").read_bytes(), blueprint)
    assert len(rows) == 4
    assert rows[0]["scores"]["Q2"] == 3.0


@pytest.mark.parametrize(
    ("csv_text", "code"),
    [
        ("student_id,student_name,Q1,Q2,Q3,Q4,Q5,Q6\nS1,A,3,0,0,0,0,0", "SCORE_OUT_OF_RANGE"),
        ("student_id,student_name,Q1,Q2,Q3,Q4,Q5\nS1,A,1,0,0,0,0", "MISSING_QUESTION"),
        ("student_id,student_name,Q1,Q2,Q3,Q4,Q5,Q6,Q9\nS1,A,1,0,0,0,0,0,0", "UNEXPECTED_QUESTION"),
        ("student_id,student_name,Q1,Q2,Q3,Q4,Q5,Q6\nS1,A,1,0,0,0,0,0\nS1,A,1,0,0,0,0,0", "DUPLICATE_STUDENT"),
        ("student_id,student_name,Q1,Q2,Q3,Q4,Q5,Q6\nS1,A,1,,0,0,0,0", "BLANK_SCORE"),
    ],
)
def test_invalid_csv_reports_precise_errors(blueprint, csv_text, code):
    with pytest.raises(IngestionError) as caught:
        parse_results_csv(csv_text.encode(), blueprint)
    assert code in {issue.code for issue in caught.value.issues}

