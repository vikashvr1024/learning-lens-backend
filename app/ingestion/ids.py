import re


def canonical_question_id(value: object) -> str:
    """Normalize a question label so equivalent writings match.

    "Q13a", "13(a)", "q13a" and " 13 A " all become "Q13a"; "Q1" and "1"
    both become "Q1". The AI-extracted blueprint and the teacher's CSV rarely
    use identical labels, so both ingestion paths compare canonical IDs while
    error messages keep the original text.
    """
    text = str(value).strip().upper()
    match = re.search(r"\d+", text)
    if not match:
        raise ValueError(f"Question ID {value!r} contains no question number.")
    letters = "".join(re.findall(r"[A-Z]", text[match.end():]))
    return f"Q{match.group(0)}{letters.lower()}"
