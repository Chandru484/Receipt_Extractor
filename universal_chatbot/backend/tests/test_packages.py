import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from universal_chatbot.backend.app.main import app
from universal_chatbot.backend.app.services.package_service import package_service
from universal_chatbot.backend.app.schemas.package_schema import PackagedQuestionsCreate


def test_package_service_dynamic_collection_separation():
    """Verify package_service separates collections by project and role."""
    mock_db = MagicMock()
    mock_admin_col = MagicMock()
    mock_worker_col = MagicMock()
    mock_user_col = MagicMock()

    mock_db.__getitem__.side_effect = lambda col_name: {
        "proj_alpha_admin_questions": mock_admin_col,
        "proj_alpha_worker_questions": mock_worker_col,
        "proj_alpha_user_questions": mock_user_col,
    }.get(col_name, MagicMock())

    with patch("universal_chatbot.backend.app.services.package_service.get_chatbot_db", return_value=mock_db):
        # 1. Save admin package
        admin_pkg = PackagedQuestionsCreate(
            project_id="proj_alpha",
            role="admin",
            package_name="Executive Insights",
            questions=["Q1 Admin", "Q2 Admin", "Q3 Admin"],
        )
        package_service.save_package(admin_pkg)
        mock_admin_col.insert_one.assert_called_once()
        mock_worker_col.insert_one.assert_not_called()

        # 2. Save worker package
        worker_pkg = PackagedQuestionsCreate(
            project_id="proj_alpha",
            role="worker",
            package_name="Factory Tasks",
            questions=["Q1 Worker", "Q2 Worker"],
        )
        package_service.save_package(worker_pkg)
        mock_worker_col.insert_one.assert_called_once()


def test_package_endpoints_and_rbac():
    """Verify REST API returns only the role's tailored questions."""
    with patch("universal_chatbot.backend.app.main.ensure_indexes"):
        client = TestClient(app)

        # 1. Query Admin suggestions
        resp_admin = client.get("/api/v1/projects/proj_demo/suggestions?role=admin")
        assert resp_admin.status_code == 200
        data_admin = resp_admin.json()
        assert data_admin["role"] == "admin"
        assert len(data_admin["suggested_questions"]) >= 5
        assert any("revenue" in q.lower() or "executive" in q.lower() for q in data_admin["suggested_questions"])

        # 2. Query Worker suggestions
        resp_worker = client.get("/api/v1/projects/proj_demo/suggestions?role=worker")
        assert resp_worker.status_code == 200
        data_worker = resp_worker.json()
        assert data_worker["role"] == "worker"
        assert any("shift" in q.lower() or "task" in q.lower() for q in data_worker["suggested_questions"])

        # 3. Query User suggestions
        resp_user = client.get("/api/v1/projects/proj_demo/suggestions?role=user")
        assert resp_user.status_code == 200
        data_user = resp_user.json()
        assert data_user["role"] == "user"
        assert any("order" in q.lower() or "invoice" in q.lower() for q in data_user["suggested_questions"])
