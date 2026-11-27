from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    source_type: Literal["website", "document", "database", "faq"]
    title: str
    url: Optional[str] = None
    page: Optional[int] = None
    snippet: Optional[str] = None


class ChatMessageRequest(BaseModel):
    website_id: Optional[str] = Field(default="site_demo", description="Target website or application ID (or project_id)")
    message: str = Field(..., min_length=1, max_length=4000, description="User prompt or question")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue")
    session_id: Optional[str] = Field(None, description="Visitor session token")
    language: Optional[str] = Field(default="en", description="Selected language ('en' for English, 'ta' for Tamil)")
    active_document_id: Optional[str] = Field(None, description="Optional document ID if asking about uploaded file")
    is_voice: bool = Field(default=False, description="Flag indicating input originated from speech/microphone")
    user_id: Optional[str] = Field(None, description="Logged-in User ID (e.g. 'usr_101')")
    admin_id: Optional[str] = Field(None, description="Logged-in Admin ID (e.g. 'adm_01') - auto-assigns admin scope")
    role: Optional[str] = Field(None, description="Role of the logged-in candidate ('admin', 'worker', 'user')")
    package_id: Optional[str] = Field(None, description="Package identifier (e.g. 'pkg_starter', 'pkg_pro')")
    package_questions: Optional[List[str]] = Field(default=None, description="Optional list of package questions sent from frontend")


class ChatMessageResponse(BaseModel):
    conversation_id: str
    message_id: str
    reply: str
    language: str
    source: Literal["website_knowledge", "user_document", "app_database", "general", "handoff"]
    citations: List[SourceCitation] = Field(default_factory=list)
    escalate_to_human: bool = False
    tawk_property_id: Optional[str] = None
    tawk_widget_id: Optional[str] = None
    tawk_direct_url: Optional[str] = None
    created_at: str
    is_voice: bool = False
    package_id: Optional[str] = Field(None, description="Associated package ID")
    sql_query: Optional[str] = Field(None, description="Generated SQL / database query executed to retrieve data")
    action: Optional[Dict[str, Any]] = Field(None, description="Executable website action triggered by voice/text command")


class ConversationSummary(BaseModel):
    conversation_id: str
    website_id: str
    title: str
    language: str
    message_count: int
    created_at: str
    updated_at: str


class EditMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Updated message content")


class ChatInitRequest(BaseModel):
    website_id: Optional[str] = Field(default="site_demo", description="Target website or project ID")
    project_id: Optional[str] = Field(default=None, description="Optional alias for website_id")
    user_id: Optional[str] = Field(default=None, description="Logged-in User ID")
    admin_id: Optional[str] = Field(default=None, description="Logged-in Admin ID")
    role: Optional[str] = Field(default="user", description="Role: 'admin', 'worker', 'user'")
    package_id: Optional[str] = Field(default=None, description="Package identifier (e.g. 'pkg_admin_01')")
    session_id: Optional[str] = Field(default=None, description="Visitor session ID")


class ChatInitResponse(BaseModel):
    status: str = "success"
    website_id: str
    user_id: Optional[str] = None
    role: str = "user"
    package_id: str = "default_pkg"
    conversation_id: str
    is_new_user: bool = True
    has_history: bool = False
    message_count: int = 0
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_questions: List[str] = Field(default_factory=list)
    package_name: Optional[str] = None

