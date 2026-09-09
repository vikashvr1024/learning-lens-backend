import io

from pypdf import PdfReader

from app.ingestion.errors import IngestionError, IngestionIssue

MAX_PDF_BYTES = 15_000_000
MAX_PDF_PAGES = 40
MAX_PDF_CHARS = 120_000
MIN_TEXT_CHARS = 200


def _issue(code: str, message: str, suggested_fix: str) -> IngestionError:
    return IngestionError(
        message,
        [IngestionIssue(
            source="blueprint_pdf", code=code, message=message, suggested_fix=suggested_fix,
        )],
    )


def extract_pdf_text(content: bytes) -> str:
    """Extract readable text from a test-paper PDF for blueprint drafting.

    Scanned-image papers have no text layer; callers fall back to a vision-capable
    provider (Gemini) with the raw PDF bytes in that case.
    """
    if not content.startswith(b"%PDF"):
        raise _issue(
            "NOT_A_PDF", "File is not a PDF document.",
            "Export or scan the test paper as a .pdf file and try again.",
        )
    if len(content) > MAX_PDF_BYTES:
        raise _issue(
            "PDF_TOO_LARGE", "Paper PDF exceeds the 15 MB limit.",
            "Compress the scan or split the paper and try again.",
        )
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as error:
        raise _issue(
            "PDF_UNREADABLE", f"PDF could not be read: {error}",
            "Re-export the paper as a standard PDF and try again.",
        ) from error
    if len(reader.pages) > MAX_PDF_PAGES:
        raise _issue(
            "PDF_TOO_LARGE", f"Paper has {len(reader.pages)} pages (limit {MAX_PDF_PAGES}).",
            "Upload only the pages containing the test questions.",
        )
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise _issue(
            "PDF_NO_TEXT",
            "No readable text found in the PDF. It looks like a scanned image.",
            "Use AI_PROVIDER=gemini so the paper can be read visually, or upload a text-based PDF.",
        )
    return text[:MAX_PDF_CHARS]
