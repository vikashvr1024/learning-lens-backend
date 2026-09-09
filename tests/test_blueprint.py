import json
from pathlib import Path

import pytest

from app.ingestion.blueprint import parse_blueprint
from app.ingestion.errors import IngestionError

ROOT = Path(__file__).resolve().parents[2]


def test_valid_blueprint_is_assessment_agnostic():
    blueprint = parse_blueprint((ROOT / "examples" / "p4_light_blueprint.json").read_bytes())
    assert blueprint.assessment.total_marks == 20
    assert len(blueprint.questions) == 6
    assert {question.topic for question in blueprint.questions} == {"Light", "Shadows"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["questions"].append(data["questions"][0].copy()), "duplicate question"),
        (lambda data: data["assessment"].update(total_marks=999), "sum to"),
        (lambda data: data["questions"][0].update(max_marks=0), "greater than 0"),
    ],
)
def test_invalid_blueprints_are_rejected(mutation, message):
    data = json.loads((ROOT / "examples" / "p4_light_blueprint.json").read_text())
    mutation(data)
    with pytest.raises(IngestionError) as caught:
        parse_blueprint(json.dumps(data))
    assert message.lower() in str(caught.value.issues[0].message).lower()

