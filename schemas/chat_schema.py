from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Message author role: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="Visitor's question or message")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Recent conversation turns for context")
    session_id: Optional[str] = Field(default=None, description="Optional visitor session identifier")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="AI generated answer in markdown format")
    escalate_to_tawk: bool = Field(default=False, description="Flag indicating if visitor should be connected to human agent on Tawk.to")
    escalation_reason: Optional[str] = Field(default=None, description="Reason for escalation (e.g. 'image_upload', 'voice_message', 'human_request')")
    suggested_questions: Optional[List[str]] = Field(
        default_factory=lambda: [
            "What file formats are supported?",
            "How do I upload a multi-page PDF?",
            "How does duplicate invoice detection work?",
            "Where is the Swagger API documentation?",
            "Connect me with a human agent"
        ],
        description="Suggested follow-up questions"
    )
