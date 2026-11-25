from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


RoleType = Literal["admin", "worker", "user", "guest"]


class PackagedQuestionsCreate(BaseModel):
    project_id: str = Field(..., description="Project / Tenant identifier")
    role: RoleType = Field(..., description="Candidate role: 'admin', 'worker', or 'user'")
    package_name: str = Field(..., description="Name or title of the package, e.g. 'Daily Tasks'")
    questions: List[str] = Field(..., min_length=1, max_length=20, description="List of questions (e.g. 10 questions)")
    target_user_id: Optional[str] = Field(None, description="Optional specific user_id if package is tailored to an individual")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or permissions")


class PackagedQuestionsResponse(BaseModel):
    package_id: str
    project_id: str
    role: RoleType
    package_name: str
    questions: List[str]
    target_user_id: Optional[str] = None
    created_at: str
    is_active: bool


class CandidateSuggestionsResponse(BaseModel):
    project_id: str
    role: RoleType
    candidate_id: Optional[str] = None
    package_name: Optional[str] = None
    suggested_questions: List[str] = Field(default_factory=list)
