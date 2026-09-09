from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class IngestionIssue:
    source: str
    message: str
    code: str
    row: int | None = None
    column: str | None = None
    expected: Any = None
    actual: Any = None
    suggested_fix: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class IngestionError(ValueError):
    def __init__(self, message: str, issues: list[IngestionIssue]):
        super().__init__(message)
        self.issues = issues

