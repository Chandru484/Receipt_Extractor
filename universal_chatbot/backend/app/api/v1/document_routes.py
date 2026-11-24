import os
from typing import Optional, List
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, status
from pydantic import BaseModel

from universal_chatbot.backend.app.services.rag_service import rag_service
from universal_chatbot.backend.app.services.tenant_service import get_website_by_id
from universal_chatbot.backend.app.database.collections import get_user_documents_collection

router = APIRouter(prefix="/documents", tags=["Documents & RAG"])

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    total_chars: int
    is_user_document: bool
    status: str
    message: str


@router.post("/upload", response_model=DocumentUploadResponse, summary="Upload user document for Q&A")
async def upload_document(
    file: UploadFile = File(...),
    website_id: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
):
    """
    Upload a document (PDF, TXT, CSV, MD, JSON) to enable grounded Q&A
    within the current chat session.
    """
    # 1. Validate website exists
    site = get_website_by_id(website_id)
    tenant_id = site.get("tenant_id", "ten_default") if site else "ten_default"

    # 2. Read and validate file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds maximum limit of 15MB.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. Ingest and chunk through RAG service
    try:
        result = rag_service.ingest_document(
            tenant_id=tenant_id,
            website_id=website_id,
            filename=file.filename or "uploaded_file",
            file_bytes=content,
            source_type="user_upload",
            conversation_id=conversation_id,
            session_id=session_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(exc)}",
        )

    return DocumentUploadResponse(
        document_id=result["source_id"],
        filename=result["filename"],
        chunk_count=result["chunk_count"],
        total_chars=result["total_chars"],
        is_user_document=result["is_user_document"],
        status="processed",
        message=f"Document '{result['filename']}' indexed into {result['chunk_count']} chunks. You can now ask questions about it.",
    )


@router.get("/conversation/{conversation_id}", summary="List documents attached to a conversation")
def list_conversation_documents(conversation_id: str):
    """Retrieve all uploaded documents associated with this conversation ID."""
    user_docs_col = get_user_documents_collection()
    if user_docs_col is None:
        return {"documents": []}
    docs = list(user_docs_col.find({"conversation_id": conversation_id}, {"_id": 0}))
    return {"conversation_id": conversation_id, "documents": docs, "count": len(docs)}
