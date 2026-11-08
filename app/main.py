import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Document
from app.parser import ExtractionError, extract_structured_data, extract_text_from_pdf
from app.schemas import DEFAULT_SCHEMA, DocumentDetailOut, DocumentOut


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="LLM Document Parser",
    description="Uploads a PDF, extracts its text, and asks an LLM to pull out structured fields.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/documents", response_model=DocumentDetailOut)
async def upload_document(
    file: UploadFile = File(...),
    schema: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Document:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only application/pdf uploads are supported")

    field_schema = DEFAULT_SCHEMA
    if schema:
        try:
            field_schema = json.loads(schema)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"`schema` must be valid JSON: {exc}") from exc

    file_bytes = await file.read()
    text = extract_text_from_pdf(file_bytes)
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract any text from the PDF")

    try:
        extracted = extract_structured_data(text, field_schema)
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    document = Document(
        filename=file.filename or "upload.pdf",
        raw_text=text,
        schema_used=field_schema,
        extracted_data=extracted,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.id.desc()).all()


@app.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
