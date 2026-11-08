import json
from io import BytesIO

import anthropic
from pypdf import PdfReader

from app.config import settings


class ExtractionError(Exception):
    """Raised when the model response can't be parsed as the requested schema."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Pull plain text out of a PDF's pages, concatenated with blank lines between them."""
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _build_prompt(text: str, schema: dict) -> str:
    schema_desc = "\n".join(f"- {field}: {desc}" for field, desc in schema.items())
    return (
        "Extract structured data from the document text below. "
        "Return ONLY a single JSON object (no markdown fences, no commentary) "
        f"with exactly these fields:\n{schema_desc}\n\n"
        "If a field isn't present in the document, use null (or an empty array "
        "for list fields). Do not invent values.\n\n"
        f"--- DOCUMENT TEXT ---\n{text}\n--- END DOCUMENT TEXT ---"
    )


def extract_structured_data(text: str, schema: dict, client: anthropic.Anthropic | None = None) -> dict:
    """Ask the LLM to pull `schema`'s fields out of `text`, returned as a dict.

    `client` is injectable so tests can pass a fake/mocked Anthropic client
    instead of hitting the real API.
    """
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": _build_prompt(text, schema)}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text").strip()

    # Models sometimes wrap JSON in ```json fences despite instructions; strip if present.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model did not return valid JSON: {raw!r}") from exc
