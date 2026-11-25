from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


RoleType = Literal["admin", "worker", "user", "guest"]


class PackagedQuestionsCreate(BaseModel):
    project_id: str = Field(..., description="Project / Tenant identifier")
    role: RoleType = Field(..., description="Candidate role: 'admin', 'worker', or 'user'")
    package_name: str = Field(..., description="Name or title of the package, e.g. 'Daily Tasks'")
    questions: List[str] = Field(..., min_length=1, max_length=30, description="List of questions (e.g. 10 questions)")
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


class CandidateLoginSessionRequest(BaseModel):
    """
    Payload sent by coworker's backend when a user/admin/worker logs in.
    Transmits candidate ID (admin_id, worker_id, or user_id), project_id, and dynamic package questions.
    """
    project_id: str = Field(..., description="Project identifier (e.g. 'proj_demo', 'proj_hospital')")
    role: RoleType = Field(default="user", description="Candidate role: 'admin', 'worker', or 'user'")
    admin_id: Optional[str] = Field(None, description="Admin identifier if role is admin")
    worker_id: Optional[str] = Field(None, description="Worker identifier if role is worker")
    user_id: Optional[str] = Field(None, description="User identifier if role is user")
    candidate_id: Optional[str] = Field(None, description="Generic candidate identifier")
    candidate_name: Optional[str] = Field(None, description="Display name of candidate")
    candidate_email: Optional[str] = Field(None, description="Email of candidate")
    package_name: Optional[str] = Field("Session Curated Package", description="Title of the question package")
    package_questions: List[str] = Field(default_factory=list, description="List of (e.g. 10) questions sent at login")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra metadata or permissions")


class CandidateLoginSessionResponse(BaseModel):
    status: str
    project_id: str
    role: str
    candidate_id: str
    session_id: str
    questions_saved: int
    suggested_questions: List[str]
    message: str


class ChatbotAdminQuestionsUpdate(BaseModel):
    """Payload used by the Chatbot Admin to modify questions for any project and role."""
    role: RoleType = Field(..., description="Target role: 'admin', 'worker', or 'user'")
    questions: List[str] = Field(..., min_length=1, max_length=50, description="Updated list of questions")
    package_name: Optional[str] = Field("Admin Modified Package", description="Updated package name")
    target_user_id: Optional[str] = Field(None, description="Optional target user ID if updating for specific person")
