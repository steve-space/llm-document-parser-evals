# LLM Document Parser

A small FastAPI service that turns unstructured PDFs (invoices, receipts,
contracts, …) into structured JSON using an LLM. Upload a PDF, get back
extracted fields you define — no hand-written regex or template matching
per document layout.

## How it works

1. `POST /documents` accepts a PDF upload and an optional JSON `schema`
   describing the fields to extract (defaults to a generic invoice schema:
   vendor, date, total, currency, line items).
2. The service extracts raw text from the PDF with `pypdf`.
3. The text + schema are sent to the LLM (Anthropic's API), which returns a
   JSON object matching the requested fields.
4. The document (filename, raw text, schema used, extracted data) is
   persisted to the database and returned to the caller.

```
POST /documents  → upload a PDF, get structured JSON back
GET  /documents  → list previously parsed documents
GET  /documents/{id} → fetch one document, including its raw text
```

## Stack

- **FastAPI** — HTTP API, request validation, OpenAPI docs (`/docs`)
- **Anthropic API** — structured extraction from free text
- **pypdf** — PDF text extraction
- **SQLAlchemy + SQLite** — persistence (swap `DATABASE_URL` for Postgres in production)
- **pytest** — unit + API tests, with the LLM client mocked so the suite
  runs with no API key and no network access
- **GitHub Actions** — CI runs the test suite and builds the Docker image on every push

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for interactive API docs, or:

```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@invoice.pdf"
```

To use a custom extraction schema instead of the default invoice one:

```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@contract.pdf" \
  -F 'schema={"parties": "array of strings", "effective_date": "string, ISO date", "term_months": "number|null"}'
```

## Running with Docker

```bash
docker build -t llm-document-parser .
docker run -p 8000:8000 --env-file .env llm-document-parser
```

## Tests

```bash
pytest -v
```

Tests don't call the real API — `app.parser.extract_structured_data` takes
an injectable `client`, so the test suite swaps in a fake one. This keeps
CI fast, free, and deterministic.

## Notes / possible extensions

- Add OCR (e.g. `pytesseract`) for scanned, non-text PDFs.
- Add a confidence/validation pass: re-ask the model to verify its own
  extraction against the source text before persisting.
- Swap SQLite for Postgres by setting `DATABASE_URL` — no code changes needed.
