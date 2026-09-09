import io

import httpx
import pytest
from pypdf import PdfWriter

import app.services.blueprint_extraction as extraction
from app.ai.providers.http_providers import GeminiProvider
from app.ingestion.errors import IngestionError
from app.ingestion.pdf_text import extract_pdf_text


def _blank_pdf() -> bytes:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    return buffer.getvalue()


DRAFT = {
    "assessment": {
        "id": "pdf-demo", "title": "Paper PDF Demo", "subject": "Science",
        "grade": "Primary 4", "total_marks": 3,
    },
    "questions": [
        {"question_id": "Q1", "question_number": 1, "max_marks": 2,
         "topic": "Light", "concept": "Sources of Light"},
        {"question_id": "Q2", "question_number": 2, "max_marks": 1,
         "topic": "Light", "concept": "Reflection"},
    ],
}


class _FakeProvider:
    name = "fake"
    model = "fake-vision-v1"

    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.calls = 0

    async def extract_blueprint(
        self, *, system_prompt, paper_text, pdf_bytes, filename, feedback=None,
    ):
        assert paper_text
        self.calls += 1
        if self.calls > 1:
            assert feedback, "retry must carry the validation error back"
        return self.drafts[min(self.calls - 1, len(self.drafts) - 1)]


def _new_assessment(client):
    return client.post("/api/v1/assessments", json={"title": "PDF intake"}).json()["id"]


def test_rejects_non_pdf_bytes():
    with pytest.raises(IngestionError) as exc_info:
        extract_pdf_text(b'{"not": "a pdf"}')
    assert exc_info.value.issues[0].code == "NOT_A_PDF"


def test_rejects_pdf_without_readable_text():
    with pytest.raises(IngestionError) as exc_info:
        extract_pdf_text(_blank_pdf())
    assert exc_info.value.issues[0].code == "PDF_NO_TEXT"


def test_pdf_endpoint_rejects_wrong_file_type(client):
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_pdf_endpoint_needs_configured_provider(client):
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AI_NOT_CONFIGURED"


def test_pdf_endpoint_saves_validated_blueprint(client, monkeypatch):
    monkeypatch.setattr(
        extraction, "get_ai_provider", lambda settings: _FakeProvider([DRAFT])
    )
    monkeypatch.setattr(
        extraction, "extract_pdf_text", lambda content: "Q1 source of light [2] Q2 mirror [1]",
    )
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "pdf"
    assert payload["validation"] == {"status": "valid", "question_count": 2, "total_marks": 3}


def test_pdf_endpoint_rejects_invalid_draft(client, monkeypatch):
    monkeypatch.setattr(
        extraction, "get_ai_provider", lambda settings: _FakeProvider([{"bogus": True}])
    )
    monkeypatch.setattr(
        extraction, "extract_pdf_text", lambda content: "Q1 source of light [2]",
    )
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BLUEPRINT_INVALID"


def test_pdf_endpoint_retries_with_validation_feedback(client, monkeypatch):
    bad_question = {key: value for key, value in DRAFT["questions"][0].items() if key != "concept"}
    bad = {"assessment": DRAFT["assessment"], "questions": [bad_question, DRAFT["questions"][1]]}
    provider = _FakeProvider([bad, DRAFT])
    monkeypatch.setattr(extraction, "get_ai_provider", lambda settings: provider)
    monkeypatch.setattr(
        extraction, "extract_pdf_text", lambda content: "Q1 source of light [2] Q2 mirror [1]",
    )
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert provider.calls == 2
    assert response.json()["validation"]["total_marks"] == 3


def test_pdf_endpoint_repairs_wrong_total_deterministically(client, monkeypatch):
    draft = {"assessment": {**DRAFT["assessment"], "total_marks": 48}, "questions": DRAFT["questions"]}
    provider = _FakeProvider([draft])
    monkeypatch.setattr(extraction, "get_ai_provider", lambda settings: provider)
    monkeypatch.setattr(
        extraction, "extract_pdf_text", lambda content: "Q1 source of light [2] Q2 mirror [1]",
    )
    assessment_id = _new_assessment(client)
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/blueprint-pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert provider.calls == 1
    assert response.json()["validation"] == {"status": "valid", "question_count": 2, "total_marks": 3}


def test_gemini_retries_transient_overload(monkeypatch):
    import asyncio

    calls = {"count": 0}

    class _Response:
        def __init__(self, status):
            self.status_code = status

        def raise_for_status(self):
            if self.status_code != 200:
                raise httpx.HTTPStatusError("overloaded", request=None, response=self)

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            calls["count"] += 1
            return _Response(503 if calls["count"] < 3 else 200)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    provider = GeminiProvider("key", "model", 60)
    result = asyncio.run(provider.extract_blueprint(
        system_prompt="s", paper_text="", pdf_bytes=b"%PDF", filename="p.pdf",
    ))
    assert result == {}
    assert calls["count"] == 3

