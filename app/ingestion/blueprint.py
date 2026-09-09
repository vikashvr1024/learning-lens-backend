import json

from pydantic import ValidationError

from app.ingestion.errors import IngestionError, IngestionIssue
from app.schemas.blueprint import Blueprint


def parse_blueprint(content: bytes | str) -> Blueprint:
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise IngestionError(
            "Blueprint is not valid JSON.",
            [IngestionIssue(
                source="blueprint",
                code="INVALID_JSON",
                message=str(error),
                suggested_fix="Export the blueprint as UTF-8 JSON and try again.",
            )],
        ) from error
    try:
        return Blueprint.model_validate(raw)
    except ValidationError as error:
        issues = [
            IngestionIssue(
                source="blueprint",
                code="SCHEMA_ERROR",
                column=".".join(str(part) for part in item["loc"]),
                message=item["msg"],
                actual=item.get("input"),
                suggested_fix="Correct this field to match the blueprint schema.",
            )
            for item in error.errors(include_url=False)
        ]
        raise IngestionError("Blueprint validation failed.", issues) from error

