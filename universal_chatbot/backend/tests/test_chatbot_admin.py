import pytest
from fastapi.testclient import TestClient
from universal_chatbot.backend.app.main import app

client = TestClient(app)


def test_serve_chatbot_admin_html():
    """Verify GET /chatbot-admin serves the dashboard."""
    resp = client.get("/chatbot-admin")
    assert resp.status_code == 200
    assert "Project Admin Portal" in resp.text


def test_login_session_ingestion_and_retrieval():
    """Verify backend login-session ingest, separation in collections, and question retrieval."""
    test_project = "proj_test_demo"
    
    # 1. Ingest Admin session
    admin_payload = {
        "project_id": test_project,
        "admin_id": "adm_test_01",
        "role": "admin",
        "candidate_email": "testadmin@company.com",
        "package_questions": [
            "Show overall system revenue",
            "List inactive workers this week",
            "Export financial summary",
        ],
    }
    resp1 = client.post("/api/v1/chatbot-admin/login-session", json=admin_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "success"
    assert data1["role"] == "admin"
    assert data1["questions_saved"] == 3

    # 2. Ingest Worker session
    worker_payload = {
        "project_id": test_project,
        "worker_id": "wrk_test_99",
        "role": "worker",
        "candidate_email": "worker99@company.com",
        "package_questions": [
            "What are my shift hours?",
            "How do I log safety issues?",
        ],
    }
    resp2 = client.post("/api/v1/chatbot-admin/login-session", json=worker_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["role"] == "worker"
    assert data2["questions_saved"] == 2

    # 3. Retrieve all questions for the project via Admin API
    resp3 = client.get(f"/api/v1/chatbot-admin/projects/{test_project}/questions")
    assert resp3.status_code == 200
    questions_data = resp3.json()
    assert questions_data["project_id"] == test_project
    assert len(questions_data["packages"]["admin"]["questions"]) >= 2
    assert len(questions_data["packages"]["worker"]["questions"]) >= 2

    # 4. Chatbot Admin updates questions for a role
    update_payload = {
        "role": "admin",
        "package_name": "Updated Admin Suite",
        "questions": [
            "Updated question 1: Realtime stats",
            "Updated question 2: Weekly audits",
        ],
    }
    resp4 = client.put(f"/api/v1/chatbot-admin/projects/{test_project}/questions", json=update_payload)
    assert resp4.status_code == 200
    assert resp4.json()["questions_count"] == 2

    # 5. Project overview
    resp5 = client.get(f"/api/v1/chatbot-admin/projects/{test_project}/data")
    assert resp5.status_code == 200
    overview = resp5.json()
    assert overview["counts"]["admins"] >= 1
    assert overview["counts"]["workers"] >= 1
