from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from universal_chatbot.backend.app.schemas.package_schema import (
    PackagedQuestionsCreate,
    PackagedQuestionsResponse,
    CandidateSuggestionsResponse,
    RoleType,
)
from universal_chatbot.backend.app.services.package_service import package_service

router = APIRouter(prefix="/projects", tags=["Project Packages & RBAC Suggestions"])


@router.post(
    "/{project_id}/packages",
    response_model=PackagedQuestionsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Push package of role-specific questions for a project (Coworker API)"
)
def upload_packaged_questions(project_id: str, payload: PackagedQuestionsCreate):
    """
    Called by your coworker's backend to push a package of (e.g. 10) questions
    tailored to a specific candidate type ('admin', 'worker', or 'user').
    Stored in a dedicated separate MongoDB collection for that role and project.
    """
    if payload.project_id != project_id:
        payload.project_id = project_id

    try:
        return package_service.save_package(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store question package: {str(exc)}"
        )


@router.get(
    "/{project_id}/suggestions",
    response_model=CandidateSuggestionsResponse,
    summary="Get interactive suggested questions for logged-in candidate (Widget API)"
)
def get_candidate_suggestions(
    project_id: str,
    role: str = Query("user", description="Logged-in candidate type: 'admin', 'worker', or 'user'"),
    candidate_id: Optional[str] = Query(None, description="Optional admin_id, worker_id, or user_id"),
):
    """
    Called by the chatbot widget when a user logs in.
    Returns the exact 10 questions for that role so the widget can display them
    as 1-click interactive suggestion chips.
    Strictly isolated: An admin collection is never accessed for worker or user requests.
    """
    try:
        clean_role = (role or "user").strip().lower()
        if clean_role not in ("admin", "worker", "user", "guest"):
            clean_role = "user"
        return package_service.get_candidate_suggestions(
            project_id=project_id,
            role=clean_role,
            candidate_id=candidate_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch suggestions: {str(exc)}"
        )
