import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(monkeypatch):
    """A TestClient wired to a fresh in-memory SQLite DB, with LLM calls mocked out."""
    # StaticPool makes every connection share the same in-memory DB instead of
    # each getting its own (SQLite's default in-memory behavior per connection).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Skip real PDF parsing / Anthropic calls entirely in API-level tests.
    monkeypatch.setattr("app.main.extract_text_from_pdf", lambda _bytes: "INVOICE #123\nAcme Corp\nTotal: $42.00")
    monkeypatch.setattr(
        "app.main.extract_structured_data",
        lambda text, schema: {
            "vendor": "Acme Corp",
            "document_date": None,
            "total_amount": 42.0,
            "currency": "USD",
            "line_items": [],
        },
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
