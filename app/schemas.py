import datetime as dt

from pydantic import BaseModel, ConfigDict

# Default extraction schema: a generic invoice/receipt. Callers can override
# this per-request by posting their own `schema` field describing the fields
# they want pulled out of the document.
DEFAULT_SCHEMA: dict = {
    "vendor": "string, the company/person issuing the document",
    "document_date": "string, ISO 8601 date if present, else null",
    "total_amount": "number, the total amount due/paid, else null",
    "currency": "string, ISO currency code if determinable, else null",
    "line_items": "array of {description: string, quantity: number|null, amount: number|null}",
}


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    schema_used: dict
    extracted_data: dict
    created_at: dt.datetime


class DocumentDetailOut(DocumentOut):
    raw_text: str
