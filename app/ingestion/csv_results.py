from io import BytesIO

import pandas as pd

from app.ingestion.errors import IngestionError, IngestionIssue
from app.ingestion.ids import canonical_question_id
from app.schemas.blueprint import Blueprint


def result_question_ids(content: bytes) -> list[str]:
    """Read canonical question IDs from a results CSV header, without a blueprint.

    Used to guide PDF blueprint extraction: the teacher's columns define the
    exact question inventory the paper must be mapped to.
    """
    try:
        frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, nrows=0)
    except Exception as error:
        raise IngestionError(
            "Performance file is not a readable CSV.",
            [IngestionIssue(
                source="performance",
                code="MALFORMED_CSV",
                message=str(error),
                suggested_fix="Save the file as UTF-8 CSV with one header row.",
            )],
        ) from error
    ids = []
    for column in frame.columns:
        if column in {"student_id", "student_name"}:
            continue
        try:
            ids.append(canonical_question_id(column))
        except ValueError:
            continue
    if not ids:
        raise IngestionError(
            "Performance file has no question columns.",
            [IngestionIssue(
                source="performance", code="MISSING_COLUMN",
                message="No question score columns found in the CSV header.",
                suggested_fix="Add one numeric column per blueprint question ID.",
            )],
        )
    return ids


def parse_results_csv(content: bytes, blueprint: Blueprint) -> list[dict]:
    try:
        frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as error:
        raise IngestionError(
            "Performance file is not a readable CSV.",
            [IngestionIssue(
                source="performance",
                code="MALFORMED_CSV",
                message=str(error),
                suggested_fix="Save the file as UTF-8 CSV with one header row.",
            )],
        ) from error

    issues: list[IngestionIssue] = []
    required_identity = {"student_id", "student_name"}
    question_ids = {question.question_id for question in blueprint.questions}

    # Headers are matched by canonical ID, so "13(a)", "Q13a" and "q13a" all
    # refer to the same blueprint question regardless of which file named it.
    header_map: dict[str, str] = {}
    canonical_seen: dict[str, str] = {}
    for column in frame.columns:
        if column in required_identity:
            continue
        try:
            key = canonical_question_id(column)
        except ValueError:
            key = column
        if key in canonical_seen:
            issues.append(IngestionIssue(
                source="performance", code="DUPLICATE_COLUMN", column=column,
                message=f"Columns {canonical_seen[key]!r} and {column!r} refer to the same question.",
                suggested_fix="Keep exactly one score column per question.",
            ))
        else:
            canonical_seen[key] = column
            header_map[column] = key
    frame = frame.rename(columns=header_map)
    columns = set(frame.columns)

    for missing in sorted(required_identity - columns):
        issues.append(IngestionIssue(
            source="performance", code="MISSING_COLUMN", column=missing,
            message=f"Performance file is missing required column {missing}.",
            expected=missing, suggested_fix=f"Add a {missing} column to the CSV header.",
        ))
    for missing in sorted(question_ids - columns):
        issues.append(IngestionIssue(
            source="performance", code="MISSING_QUESTION", column=missing,
            message=f"Performance file is missing question {missing}.",
            expected=missing, suggested_fix=f"Add a {missing} score column.",
        ))
    known = required_identity | question_ids
    for unexpected in sorted(columns - known):
        original = canonical_seen.get(unexpected, unexpected)
        issues.append(IngestionIssue(
            source="performance", code="UNEXPECTED_QUESTION", column=original,
            message=f"Performance file contains {original}, but it does not exist in the blueprint.",
            actual=original, suggested_fix=f"Remove {original} or add it to the blueprint.",
        ))
    if issues:
        raise IngestionError("Performance file columns do not match the blueprint.", issues)

    duplicate_ids = frame.loc[frame["student_id"].duplicated(keep=False), "student_id"].unique()
    for student_id in duplicate_ids:
        issues.append(IngestionIssue(
            source="performance", code="DUPLICATE_STUDENT", column="student_id",
            message=f"Student {student_id} appears more than once.", actual=student_id,
            suggested_fix="Keep exactly one row per student in this upload.",
        ))

    max_marks = {question.question_id: question.max_marks for question in blueprint.questions}
    records: list[dict] = []
    for index, row in frame.iterrows():
        csv_row = index + 2
        student_id = row["student_id"].strip()
        student_name = row["student_name"].strip()
        if not student_id or not student_name:
            column = "student_id" if not student_id else "student_name"
            issues.append(IngestionIssue(
                source="performance", code="BLANK_IDENTITY", row=csv_row, column=column,
                message=f"Row {csv_row} has a blank {column}.",
                suggested_fix=f"Provide a value for {column}.",
            ))
        scores: dict[str, float] = {}
        for question_id, maximum in max_marks.items():
            value = row[question_id].strip()
            if value == "":
                issues.append(IngestionIssue(
                    source="performance", code="BLANK_SCORE", row=csv_row, column=question_id,
                    message=f"Student {student_id or csv_row} has no score for {question_id}.",
                    expected=f"A number from 0 to {maximum:g}", actual="blank",
                    suggested_fix="Enter the awarded mark; do not leave score cells blank.",
                ))
                continue
            try:
                score = float(value)
            except ValueError:
                issues.append(IngestionIssue(
                    source="performance", code="NON_NUMERIC_SCORE", row=csv_row, column=question_id,
                    message=f"{question_id} has non-numeric score {value!r} for student {student_id}.",
                    expected=f"A number from 0 to {maximum:g}", actual=value,
                    suggested_fix="Replace the value with the awarded numeric mark.",
                ))
                continue
            if score < 0 or score > maximum:
                relation = "below 0" if score < 0 else f"above the maximum of {maximum:g}"
                issues.append(IngestionIssue(
                    source="performance", code="SCORE_OUT_OF_RANGE", row=csv_row,
                    column=question_id,
                    message=(f"{question_id} has a score of {score:g} for student {student_id}, "
                             f"but it is {relation}."),
                    expected=f"0 to {maximum:g}", actual=score,
                    suggested_fix="Correct the awarded mark in the CSV; marks are never auto-repaired.",
                ))
            scores[question_id] = score
        records.append({"student_id": student_id, "student_name": student_name, "scores": scores})

    if issues:
        raise IngestionError("Performance file validation failed.", issues)
    return records

