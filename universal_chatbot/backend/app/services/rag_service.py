import math
import re
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from universal_chatbot.backend.app.database.collections import (
    get_document_chunks_collection,
    get_knowledge_sources_collection,
    get_user_documents_collection,
)
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str
from universal_chatbot.backend.app.services.document_parser import (
    extract_text_from_bytes,
    chunk_text,
)


import string


def _tokenize(text: str) -> List[str]:
    """Tokenize text supporting English words and Unicode / Tamil scripts cleanly."""
    raw_words = text.lower().split()
    tokens = []
    for w in raw_words:
        cleaned = "".join(c for c in w if c not in string.punctuation and not c.isspace())
        if len(cleaned) > 1:
            tokens.append(cleaned)
    return tokens


def _compute_relevance_score(query_tokens: List[str], chunk_text: str) -> float:
    """Compute normalized term-frequency match score between query and chunk."""
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk_text)
    if not chunk_tokens:
        return 0.0

    score = 0.0
    chunk_token_set = set(chunk_tokens)
    for q_token in query_tokens:
        if q_token in chunk_token_set:
            # Term frequency in chunk
            tf = chunk_tokens.count(q_token) / len(chunk_tokens)
            score += 1.0 + (tf * 5.0)
            
            # Exact phrase bonus if query token length > 3
            if len(q_token) > 3 and q_token in chunk_text.lower():
                score += 0.5

    return score / len(query_tokens)


class RAGService:
    """RAG & Knowledge indexing service with multi-tenant isolation and session scoping."""

    def ingest_document(
        self,
        tenant_id: str,
        website_id: str,
        filename: str,
        file_bytes: bytes,
        source_type: str = "file",
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse, chunk, and index an uploaded document or knowledge source."""
        source_id = f"doc_{uuid.uuid4().hex[:12]}"
        extracted_text = extract_text_from_bytes(file_bytes, filename)
        
        chunks = chunk_text(extracted_text, chunk_size=600, chunk_overlap=100)
        now_str = get_ist_now_str()

        # 1. Store metadata
        is_user_doc = bool(conversation_id or session_id)
        if is_user_doc:
            user_docs_col = get_user_documents_collection()
            if user_docs_col is not None:
                user_docs_col.insert_one({
                    "document_id": source_id,
                    "website_id": website_id,
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "filename": filename,
                    "total_chars": len(extracted_text),
                    "chunk_count": len(chunks),
                    "created_at": now_str,
                })
        else:
            know_col = get_knowledge_sources_collection()
            if know_col is not None:
                know_col.insert_one({
                    "source_id": source_id,
                    "tenant_id": tenant_id,
                    "website_id": website_id,
                    "source_type": source_type,
                    "title": filename,
                    "chunk_count": len(chunks),
                    "status": "indexed",
                    "created_at": now_str,
                })

        # 2. Store chunks
        chunks_col = get_document_chunks_collection()
        chunk_docs = []
        for c in chunks:
            chunk_doc = {
                "chunk_id": f"chk_{uuid.uuid4().hex[:12]}",
                "source_id": source_id,
                "tenant_id": tenant_id,
                "website_id": website_id,
                "source_name": filename,
                "is_user_document": is_user_doc,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "chunk_index": c["chunk_index"],
                "content": c["text"],
                "char_count": c["char_count"],
                "created_at": now_str,
            }
            chunk_docs.append(chunk_doc)

        if chunk_docs and chunks_col is not None:
            chunks_col.insert_many(chunk_docs)

        return {
            "source_id": source_id,
            "filename": filename,
            "total_chars": len(extracted_text),
            "chunk_count": len(chunks),
            "is_user_document": is_user_doc,
        }

    def retrieve_relevant_chunks(
        self,
        tenant_id: str,
        website_id: str,
        query: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 4,
    ) -> List[Dict[str, Any]]:
        """Retrieve most relevant knowledge chunks matching user query within tenant & session boundary."""
        chunks_col = get_document_chunks_collection()
        if chunks_col is None:
            return []

        # Scope query: Website general knowledge OR user's session-specific documents
        query_filter: Dict[str, Any] = {
            "website_id": website_id,
            "tenant_id": tenant_id,
            "$or": [
                {"is_user_document": False},
                {"is_user_document": {"$exists": False}},
            ]
        }
        if conversation_id or session_id:
            conditions = []
            if conversation_id:
                conditions.append({"conversation_id": conversation_id})
            if session_id:
                conditions.append({"session_id": session_id})
            query_filter["$or"].extend(conditions)

        # Fetch candidate chunks
        candidates = list(chunks_col.find(query_filter).limit(100))
        if not candidates:
            return []

        query_tokens = _tokenize(query)
        scored_chunks = []
        for c in candidates:
            score = _compute_relevance_score(query_tokens, c.get("content", ""))
            if score > 0.05:  # Minimum relevance threshold
                scored_chunks.append({
                    "chunk_id": c.get("chunk_id"),
                    "source_name": c.get("source_name", "Document"),
                    "content": c.get("content", ""),
                    "chunk_index": c.get("chunk_index", 0),
                    "score": score,
                    "is_user_document": c.get("is_user_document", False),
                })

        # Sort descending by relevance score
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]


rag_service = RAGService()
