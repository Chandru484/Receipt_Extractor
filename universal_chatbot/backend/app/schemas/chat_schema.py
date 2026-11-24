from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    source_type: Literal["website", "document", "database", "faq"]
    title: str
    url: Optional[str] = None
    page: Optional[int] = None
    snippet: Optional[str] = None


class ChatMessageRequest(BaseModel):
    website_id: str = Field(..., description="Target website or application ID")
    message: str = Field(..., min_length=1, max_length=4000, description="User prompt or question")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue")
    session_id: Optional[str] = Field(None, description="Visitor session token")
    language: Literal["en", "ta"] = Field(default="en", description="Selected language ('en' for English, 'ta' for Tamil)")
    active_document_id: Optional[str] = Field(None, description="Optional document ID if asking about uploaded file")


class ChatMessageResponse(BaseModel):
    conversation_id: str
    message_id: str
    reply: str
    language: str
    source: Literal["website_knowledge", "user_document", "app_database", "general", "handoff"]
    citations: List[SourceCitation] = Field(default_factory=list)
    escalate_to_human: bool = False
    tawk_property_id: Optional[str] = None
    created_at: str


class ConversationSummary(BaseModel):
    conversation_id: str
    website_id: str
    title: str
    language: str
    message_count: int
    created_at: str
    updated_at: str
