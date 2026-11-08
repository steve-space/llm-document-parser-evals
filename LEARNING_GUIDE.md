# LLM Document Parser — Learning Guide

This document walks through **everything** that went into this project: what
it does, why each piece exists, every command that was run, and what each
part of the code means. Read it top to bottom if you're new to this, or jump
to a section using the table of contents.

## Table of contents

1. [What is this project, and why does it exist?](#1-what-is-this-project-and-why-does-it-exist)
2. [Concepts you need before reading the code](#2-concepts-you-need-before-reading-the-code)
3. [How the project was built, step by step](#3-how-the-project-was-built-step-by-step)
4. [Running it yourself](#4-running-it-yourself)
5. [How the tests work](#5-how-the-tests-work)
6. [Docker and CI/CD explained](#6-docker-and-cicd-explained)
7. [Publishing to GitHub](#7-publishing-to-github)
8. [What to remember / talk about in an interview](#8-what-to-remember--talk-about-in-an-interview)

---

## 1. What is this project, and why does it exist?

Companies deal with huge numbers of PDFs — invoices, receipts, contracts —
and historically the only ways to pull data out of them were:

- **Manual data entry** (slow, expensive, error-prone), or
- **Template-based parsing** (a script that expects the invoice to always
  look exactly the same — breaks the moment a vendor changes their layout).

Large Language Models (LLMs) changed this: instead of writing a parser for
every possible document layout, you extract the raw text and simply *ask*
the model to pull out the fields you care about, in a format you define.
This project is a small, real, working example of that pattern — the kind
of "LLM meets a boring business problem" project that's very common in
real jobs right now.

**What it actually does:**

1. You upload a PDF.
2. The service extracts the raw text from it.
3. It sends that text to Claude (Anthropic's LLM) along with a description
   of which fields you want (vendor name, date, total, etc.).
4. Claude replies with structured JSON matching those fields.
5. The result is saved to a database and returned to you.

## 2. Concepts you need before reading the code

| Term | What it means here |
|---|---|
| **REST API** | A web service you talk to over HTTP with URLs like `/documents`, using standard verbs (`GET`, `POST`) and JSON. |
| **FastAPI** | A Python web framework for building REST APIs. It reads your function's type hints and automatically validates requests, generates docs, etc. |
| **ORM (Object-Relational Mapper)** | A library that lets you work with database rows as Python objects instead of writing raw SQL. We use **SQLAlchemy**. |
| **Pydantic model** | A Python class that defines a data shape (fields + types) and validates data against it automatically. FastAPI uses these for request/response bodies. |
| **Dependency Injection (`Depends`)** | FastAPI's way of saying "before running this endpoint function, first run this other function and pass me its result." We use it to hand each request a fresh database session. |
| **Environment variables / `.env` file** | Configuration (like API keys) kept *outside* the code, so secrets never get committed to git. |
| **Mocking** | In tests, replacing a real dependency (like a paid API call to Claude) with a fake stand-in, so tests run fast, free, and without internet access. |

## 3. How the project was built, step by step

### Step 1 — Create the folder structure

```bash
mkdir -p llm-document-parser/{app,tests,.github/workflows}
cd llm-document-parser && git init -q
```

- `mkdir -p` creates nested folders in one go; the `{app,tests,...}` syntax
  is shell "brace expansion" — it creates all three folders at once.
- `app/` holds the actual application code.
- `tests/` holds the automated tests.
- `.github/workflows/` is a special folder GitHub looks in for **CI/CD
  pipeline** definitions (explained in section 6).
- `git init` turns the folder into a git repository, so we can track
  changes and eventually push it to GitHub.

### Step 2 — `requirements.txt`

This file lists every Python package the project depends on, pinned to an
exact version (e.g. `fastapi==0.115.0`). Pinning versions means "this exact
version is what I tested with" — so the project behaves the same on your
machine as anyone else's. You install everything in it with:

```bash
pip install -r requirements.txt
```

Packages used and why:
- `fastapi`, `uvicorn` — the web framework and the server that runs it.
- `anthropic` — the official Python client for calling Claude's API.
- `pypdf` — extracts plain text out of a PDF file.
- `sqlalchemy` — the ORM for talking to the database.
- `pydantic`, `pydantic-settings` — data validation and settings loading.
- `pytest`, `httpx` — testing tools (`httpx` is what FastAPI's test client
  uses under the hood to simulate HTTP requests without a real server).

### Step 3 — `.gitignore` and `.env.example`

`.gitignore` lists files git should never track — `__pycache__/` (Python's
compiled bytecode cache), `.venv/` (the virtual environment, which is huge
and machine-specific), and importantly `.env` (which holds your **real**
API key — never commit secrets to git!).

`.env.example` is a *template* showing what variables are needed
(`ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `DATABASE_URL`) without the real
values. Anyone cloning the repo copies it to `.env` and fills in their own key.

### Step 4 — `app/config.py`: loading configuration

```python
class Settings(BaseSettings):
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    database_url: str = "sqlite:///./documents.db"

settings = Settings()
```

`BaseSettings` (from `pydantic-settings`) automatically reads values from
environment variables (or a `.env` file) and matches them to these fields
by name. This means the rest of the code never has to call `os.environ`
directly — it just imports `settings` and uses `settings.anthropic_api_key`.
This is called the **twelve-factor app** pattern: config lives in the
environment, not hardcoded in the code.

### Step 5 — `app/database.py`: connecting to the database

```python
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- The **engine** is SQLAlchemy's connection to the actual database file
  (SQLite here — a whole database stored in a single local file, perfect
  for a small demo project; you'd swap in Postgres for a real production app).
- `Base` is a marker class every database *model* (table) will inherit from.
- `get_db()` is a **generator function** used as a FastAPI dependency: it
  hands each incoming request its own database session, and guarantees
  the session gets closed afterward (the `finally` block) even if the
  request crashes. `yield` here means "pause, hand this value to whoever
  asked for it, and resume once they're done with it."

### Step 6 — `app/models.py`: the database table

```python
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text)
    schema_used: Mapped[dict] = mapped_column(JSON)
    extracted_data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=...)
```

This class **is** the `documents` table. Each attribute is a column. This
is the "M" (Model) in ORM — a Python class that SQLAlchemy translates into
SQL `CREATE TABLE` statements and `INSERT`/`SELECT` queries for you, so you
never write raw SQL by hand.

### Step 7 — `app/schemas.py`: request/response shapes

These are *different* from the database model above — they define what
JSON goes **in and out of the API**, not what's stored in the database.
Keeping them separate is deliberate: you might not want to expose every
database column to API callers (e.g. internal fields), and the two often
need to evolve independently.

```python
DEFAULT_SCHEMA = {
    "vendor": "string, the company/person issuing the document",
    ...
}
```

This is the *default* description of what fields to extract if the caller
doesn't specify their own — it doubles as the prompt instructions sent to Claude.

### Step 8 — `app/parser.py`: the actual "LLM" part

Two functions:

```python
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()
```

Takes raw PDF bytes, opens them with `pypdf`, and pulls the text out of
every page, joining them together.

```python
def extract_structured_data(text: str, schema: dict, client=None) -> dict:
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": _build_prompt(text, schema)}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    ...
    return json.loads(raw)
```

This builds a prompt (`_build_prompt`) that says "here's the document text,
here are the fields I want, reply with only JSON," sends it to Claude, and
parses the reply back into a Python dictionary. A few defensive touches:

- `client: anthropic.Anthropic | None = None` — the **dependency is
  injectable**. In normal use it creates a real client; in tests, we pass
  in a fake one instead, so tests never make a real network call. This is
  the single most important trick for testing anything that talks to an
  external API.
- The code strips ` ```json ` markdown fences if the model adds them
  despite being told not to — LLMs are usually but not perfectly obedient,
  so you code defensively around that.
- If the reply still isn't valid JSON, we raise a custom `ExtractionError`
  rather than let a cryptic `json.JSONDecodeError` bubble up — this makes
  the failure mode explicit and easy to handle upstream.

### Step 9 — `app/main.py`: wiring it into a REST API

```python
@app.post("/documents", response_model=DocumentDetailOut)
async def upload_document(
    file: UploadFile = File(...),
    schema: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Document:
    ...
```

This is a FastAPI **route**: `@app.post("/documents", ...)` means "when
someone sends a `POST` request to `/documents`, run this function."

- `file: UploadFile = File(...)` — FastAPI parses a multipart file upload
  automatically and hands you a file-like object.
- `db: Session = Depends(get_db)` — this is the dependency injection from
  step 5: FastAPI calls `get_db()` for you and hands the resulting session
  in as `db`.
- The function reads the file, extracts text, calls Claude, saves a
  `Document` row, and returns it. FastAPI automatically converts the
  returned `Document` object into JSON matching `DocumentDetailOut`
  (the Pydantic schema from step 7), and validates it on the way out.

Two more routes, `GET /documents` and `GET /documents/{id}`, just query
the database and return results — standard **CRUD** (Create, Read, Update,
Delete — this project only needed Create and Read).

### Step 10 — Writing the tests

Tests live in `tests/`. The key file is `tests/conftest.py`, which
`pytest` automatically loads before running any test in that folder — it's
where shared setup ("fixtures") lives.

```python
@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, ...)
    ...
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main.extract_structured_data", lambda text, schema: {...})
    with TestClient(app) as test_client:
        yield test_client
```

Three important ideas here:

1. **A fresh in-memory SQLite database per test** — `sqlite://` with no
   path creates a database that lives only in memory and disappears when
   the test ends. `poolclass=StaticPool` is a fix for a subtle bug: by
   default, SQLAlchemy would give each new connection its *own* separate
   in-memory database, so your test's `INSERT` and its later `SELECT`
   would silently talk to two different empty databases. `StaticPool`
   forces every connection in that test to reuse the same one.
2. **`app.dependency_overrides`** — FastAPI lets you swap out a real
   dependency (`get_db`, which talks to the real database) for a fake one,
   *only during tests*, without touching the application code at all.
3. **`monkeypatch.setattr(...)`** — replaces `extract_structured_data`
   with a function that returns a fixed, fake result instead of calling
   the real Claude API. This is what makes the whole test suite runnable
   with **no API key and no internet connection**.

`tests/test_api.py` then tests the HTTP layer (upload a file, check the
response), and `tests/test_parser.py` unit-tests `parser.py` directly,
using a small fake `anthropic` client class instead of the real SDK.

### Step 11 — Installing dependencies and running tests for real

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

- `python3 -m venv .venv` creates an isolated **virtual environment** — a
  private copy of Python just for this project, so its package versions
  never conflict with any other project's on your machine.
- `source .venv/bin/activate` switches your terminal into that environment
  (you'll see `(.venv)` appear in your prompt).
- `pytest -v` runs every test file matching `test_*.py`, `-v` for verbose
  (prints each test name and pass/fail individually).

While building this, `pip install` initially failed — the system's default
Python was version 3.14, and one dependency (`pydantic-core`) didn't have
a pre-built package for that version yet, so pip tried to compile it from
source and failed because the build tools (Xcode) weren't fully set up.
**Fix:** recreated the virtual environment using Python 3.13 instead,
which had a pre-built package available — no compiling needed. This is a
common real-world hiccup: brand-new Python versions often lag behind on
pre-built package availability.

### Step 12 — Verifying it actually runs, not just passes tests

```bash
uvicorn app.main:app --port 8001 &
curl http://localhost:8001/health
```

Passing tests proves the *logic* works in isolation. Actually starting the
server and hitting it with `curl` (a command-line HTTP client) proves the
*whole thing* boots correctly — imports resolve, the database initializes,
routes are wired up. Both checks matter; neither replaces the other.

## 4. Running it yourself

```bash
cd llm-document-parser
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set your real ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

Then open `http://localhost:8000/docs` — FastAPI auto-generates an
interactive page (via a spec called **OpenAPI/Swagger**) where you can
try every endpoint directly in the browser, no `curl` needed.

## 5. How the tests work

Run them with:

```bash
pytest -v
```

All 8 tests pass without needing a real Claude API key, because (as
explained in step 10) the Claude client and PDF parsing are swapped for
fakes during tests. This is intentional: **tests should be fast, free, and
runnable by anyone (including a CI server) with zero external
dependencies.**

## 6. Docker and CI/CD explained

**Docker** packages the app plus everything it needs (Python, the exact
package versions) into one portable image, so it runs identically on any
machine — no "works on my machine" problems.

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Each line is a "layer": start from a small Python base image, install
dependencies (this layer is cached and only re-runs if `requirements.txt`
changes — this ordering is a deliberate optimization), copy in the app
code, and define the command that starts the server when the container runs.

**CI/CD** (Continuous Integration / Continuous Deployment) means: every
time code is pushed, a server automatically checks it still works.
`.github/workflows/ci.yml` tells **GitHub Actions** (GitHub's built-in CI
system) to, on every push:

1. Check out the code
2. Install Python + the dependencies
3. Run `pytest -v`
4. Run `docker build` to make sure the Dockerfile itself is valid

If any step fails, GitHub shows a red ❌ on the commit — you never merge
broken code without knowing it.

## 7. Publishing to GitHub

```bash
gh auth login          # one-time: log the GitHub CLI into your account
gh repo create llm-document-parser --public --source=. --remote=origin --push
```

- `gh` is GitHub's official command-line tool. `gh auth login` opens a
  device-code flow: it shows you a code, you enter it at
  github.com/login/device in a browser, and your terminal becomes
  authenticated.
- `gh repo create ... --source=. --remote=origin --push` does three things
  in one command: creates a new empty repo on your GitHub account, points
  your local git repo at it (`git remote add origin ...` under the hood),
  and pushes your code.

**A real issue we hit and fixed:** pushing a repo that includes a
`.github/workflows/*.yml` file requires the `workflow` OAuth scope, which
a freshly-authenticated `gh` token doesn't have by default. The fix:

```bash
gh auth refresh -h github.com -s workflow
```

This re-runs the device-code login, this time requesting the extra
permission, without needing to fully log out and back in.

## 8. What to remember / talk about in an interview

- **Dependency injection for testability**: `extract_structured_data`
  takes an optional `client` parameter specifically so it can be tested
  without hitting a real, paid, network-dependent API. This pattern
  generalizes to *any* external service (payment processors, email
  senders, other APIs).
- **Separation of concerns**: database models (`models.py`), API
  schemas (`schemas.py`), and business logic (`parser.py`) are three
  separate files, not one giant file. Each one has a single job.
- **Config via environment variables**, never hardcoded secrets.
- **The full loop**: write code → write tests that don't depend on
  external services → automate running those tests on every push (CI) →
  package the app so it runs anywhere (Docker).
