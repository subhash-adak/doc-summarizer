import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from main import app


@pytest.fixture(scope="module")
def client():
    # Force demo mode to True for integration tests to avoid Google API errors
    settings = get_settings()
    original_demo_mode = settings.demo_mode
    settings.demo_mode = True

    # Use TestClient as context manager to trigger lifespan events
    with TestClient(app) as c:
        yield c

    settings.demo_mode = original_demo_mode


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_auth_status(client):
    response = client.get("/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert "authenticated" in data
    assert data["demo_mode"] is True


def test_auth_login(client):
    response = client.get("/auth/login", follow_redirects=False)
    # Under demo mode, it immediately redirects to the callback endpoint
    assert response.status_code == 307
    assert "/auth/callback" in response.headers["location"]


def test_auth_callback(client):
    # Simulate callback
    response = client.get("/auth/callback?code=mock_code&state=mock_state", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_list_documents(client):
    # First authenticate the client session
    client.get("/auth/login")  # sets up mock session / token

    response = client.get("/api/documents/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 4
    assert len(data["files"]) == 4
    filenames = [f["name"] for f in data["files"]]
    assert "q3_financial_report.pdf" in filenames
    assert "marketing_strategy_v2.docx" in filenames
    assert "server_configuration_guide.txt" in filenames
    assert "empty_document.txt" in filenames


def test_summarize_and_download_reports(client):
    # Log in
    client.get("/auth/login")

    # 1. Summarize
    summarize_payload = {
        "file_ids": ["mock-file-1", "mock-file-2", "mock-file-4"]
    }
    response = client.post("/api/documents/summarize", json=summarize_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["succeeded"] == 2
    assert data["failed"] == 0

    results = data["results"]
    assert results[0]["file"]["name"] == "q3_financial_report.pdf"
    assert results[0]["status"] == "completed"
    assert "revenue" in results[0]["summary"].lower()

    assert results[2]["file"]["name"] == "empty_document.txt"
    assert results[2]["status"] == "skipped"

    # 2. Download CSV Report
    csv_response = client.get("/api/reports/csv")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    csv_content = csv_response.text
    assert "q3_financial_report.pdf" in csv_content
    assert "completed" in csv_content
    assert "empty_document.txt" in csv_content
    assert "skipped" in csv_content

    # 3. Download PDF Report
    pdf_response = client.get("/api/reports/pdf")
    assert pdf_response.status_code == 200
    assert "application/pdf" in pdf_response.headers["content-type"]
    assert len(pdf_response.content) > 0
