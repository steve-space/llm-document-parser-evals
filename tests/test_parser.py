from dataclasses import dataclass

import pytest

from app.parser import ExtractionError, extract_structured_data, extract_text_from_pdf


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeResponse:
    content: list


class _FakeMessages:
    def __init__(self, reply_text: str):
        self._reply_text = reply_text

    def create(self, **_kwargs):
        return _FakeResponse(content=[_FakeTextBlock(text=self._reply_text)])


class _FakeAnthropicClient:
    def __init__(self, reply_text: str):
        self.messages = _FakeMessages(reply_text)


def test_extract_structured_data_parses_plain_json():
    fake_client = _FakeAnthropicClient('{"vendor": "Acme", "total_amount": 10}')
    result = extract_structured_data("some invoice text", {"vendor": "string", "total_amount": "number"}, client=fake_client)
    assert result == {"vendor": "Acme", "total_amount": 10}


def test_extract_structured_data_strips_markdown_fences():
    fake_client = _FakeAnthropicClient('```json\n{"vendor": "Acme"}\n```')
    result = extract_structured_data("text", {"vendor": "string"}, client=fake_client)
    assert result == {"vendor": "Acme"}


def test_extract_structured_data_raises_on_invalid_json():
    fake_client = _FakeAnthropicClient("not json at all")
    with pytest.raises(ExtractionError):
        extract_structured_data("text", {"vendor": "string"}, client=fake_client)


def test_extract_text_from_pdf_handles_empty_pdf():
    # A PDF with no pages should yield empty text, not raise.
    from pypdf import PdfWriter
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)

    text = extract_text_from_pdf(buf.getvalue())
    assert text == ""
