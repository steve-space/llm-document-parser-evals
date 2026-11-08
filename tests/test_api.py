def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_rejects_non_pdf(client):
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_and_fetch_document(client):
    upload = client.post(
        "/documents",
        files={"file": ("invoice.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["filename"] == "invoice.pdf"
    assert body["extracted_data"]["vendor"] == "Acme Corp"
    assert body["extracted_data"]["total_amount"] == 42.0

    document_id = body["id"]

    fetched = client.get(f"/documents/{document_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == document_id

    listed = client.get("/documents")
    assert listed.status_code == 200
    assert any(doc["id"] == document_id for doc in listed.json())


def test_get_missing_document_404s(client):
    response = client.get("/documents/999999")
    assert response.status_code == 404
