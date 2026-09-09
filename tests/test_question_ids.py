from pathlib import Path

import pytest

from app.ingestion.blueprint import parse_blueprint
from app.ingestion.csv_results import parse_results_csv
from app.ingestion.errors import IngestionError
from app.ingestion.ids import canonical_question_id

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_question_id_styles():
    assert canonical_question_id("Q13a") == "Q13a"
    assert canonical_question_id("13(a)") == "Q13a"
    assert canonical_question_id("q13a") == "Q13a"
    assert canonical_question_id("14(a)(ii)") == "Q14aii"
    assert canonical_question_id("Q1") == "Q1"
    assert canonical_question_id(" 1 ") == "Q1"
    with pytest.raises(ValueError):
        canonical_question_id("total")


def test_blueprint_ids_canonicalized():
    raw = (ROOT / "examples" / "p4_light_blueprint.json").read_text()
    blueprint = parse_blueprint(raw.replace('"Q1"', '"1"').replace('"Q2"', '"2"'))
    assert [question.question_id for question in blueprint.questions][:2] == ["Q1", "Q2"]


def test_csv_headers_match_blueprint_in_any_style():
    blueprint = parse_blueprint((ROOT / "examples" / "p4_light_blueprint.json").read_bytes())
    content = b"student_id,student_name,1,2,3,4,5,6\nS1,Ana,2,3,3,4,4,4\n"
    records = parse_results_csv(content, blueprint)
    assert records[0]["scores"] == {"Q1": 2, "Q2": 3, "Q3": 3, "Q4": 4, "Q5": 4, "Q6": 4}


def test_duplicate_labels_rejected():
    blueprint = parse_blueprint((ROOT / "examples" / "p4_light_blueprint.json").read_bytes())
    content = b"student_id,student_name,Q1,1,Q3,Q4,Q5,Q6\nS1,Ana,2,2,3,4,4,4\n"
    with pytest.raises(IngestionError) as exc_info:
        parse_results_csv(content, blueprint)
    assert exc_info.value.issues[0].code == "DUPLICATE_COLUMN"
