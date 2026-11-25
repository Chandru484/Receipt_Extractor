from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status

from universal_chatbot.backend.app.schemas.package_schema import (
    CandidateLoginSessionRequest,
    CandidateLoginSessionResponse,
    ChatbotAdminQuestionsUpdate,
)
from universal_chatbot.backend.app.services.package_service import package_service

router = APIRouter(prefix="/chatbot-admin", tags=["Chatbot Project Admin Portal"])


@router.post(
    "/login-session",
    response_model=CandidateLoginSessionResponse,
    summary="Coworker Login-Session API: Transmits candidate ID, role, project_id, and dynamic package questions"
)
def handle_candidate_login_session(payload: CandidateLoginSessionRequest):
    """
    Called by your coworker's backend whenever an admin, worker, or user logs in.
    Transmits:
      - project_id
      - admin_id OR user_id OR worker_id
      - role ('admin', 'worker', 'user')
      - package_questions: List of questions for this session
    The chatbot automatically records the candidate and stores the questions in MongoDB.
    """
    try:
        return package_service.process_login_session(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process candidate login session: {str(exc)}"
        )


@router.get(
    "/projects",
    summary="Chatbot Admin: List all projects across the platform"
)
def list_projects():
    """Returns all projects registered in the Chatbot platform."""
    try:
        return {"projects": package_service.list_all_active_projects()}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list projects: {str(exc)}"
        )


@router.get(
    "/projects/{project_id}/questions",
    summary="Chatbot Admin: View all question packages for a project (Admin, Worker, User)"
)
def get_project_questions(project_id: str):
    """
    Chatbot Admin endpoint to inspect current question packages for all 3 candidate types.
    """
    try:
        return package_service.get_project_all_packages(project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load project questions: {str(exc)}"
        )


@router.put(
    "/projects/{project_id}/questions",
    summary="Chatbot Admin: Modify/edit questions for any role in any project"
)
def modify_project_questions(project_id: str, payload: ChatbotAdminQuestionsUpdate):
    """
    Chatbot Admin endpoint to update, add, or customize the questions for any role.
    Changes take effect immediately for that project's candidates.
    """
    try:
        return package_service.admin_modify_questions(project_id, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update questions: {str(exc)}"
        )


@router.get(
    "/projects/{project_id}/data",
    summary="Chatbot Admin: Inspect project candidates, conversations, and data activity"
)
def get_project_data_overview(project_id: str):
    """
    Chatbot Admin endpoint to view candidates and activity in any project.
    """
    try:
        return package_service.get_project_data_overview(project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load project data: {str(exc)}"
        )
