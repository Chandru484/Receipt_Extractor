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
    """Tokenize text supporting English words, filenames (e.g. GST.pdf -> gst, pdf), and Tamil scripts cleanly."""
    raw_words = re.split(r"[\s\.,;:!?()\[\]{}\"'/\\|+=_-]+", text.lower())
    return [w for w in raw_words if len(w) > 1]


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
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve most relevant knowledge chunks matching user query within tenant & session boundary."""
        # 0. Greetings must never pull document citations
        GREETING_WORDS = {
            "hello", "hi", "hey", "vanakkam", "வணக்கம்", "ஹலோ", "வணக்கங்கள்",
            "good morning", "good evening", "good afternoon", "welcome", "thanks", "நன்றி"
        }
        query_words = set(re.findall(r"\w+", query.lower()))
        is_greeting = bool(query_words.intersection(GREETING_WORDS)) and len(query_words) <= 3
        if is_greeting:
            return []

        chunks_col = get_document_chunks_collection()
        if chunks_col is None:
            return []

        query_tokens = _tokenize(query)
        scored_chunks: List[Dict[str, Any]] = []

        # 1. Prioritize user-uploaded documents scoped strictly to this conversation or session
        user_candidates: List[Dict[str, Any]] = []
        user_query_conditions = []
        if conversation_id and not conversation_id.startswith("conv_support"):
            user_query_conditions.append({"conversation_id": conversation_id})
        if session_id:
            user_query_conditions.append({"session_id": session_id})

        if user_query_conditions:
            user_filter: Dict[str, Any] = {
                "website_id": website_id,
                "tenant_id": tenant_id,
                "is_user_document": True,
                "$or": user_query_conditions,
            }
            user_candidates = list(chunks_col.find(user_filter).sort("_id", -1).limit(100))

        user_scored: List[Dict[str, Any]] = []
        if user_candidates:
            # Check if query specifically references a specific uploaded document filename
            target_source_id = None
            for c in user_candidates:
                s_name = c.get("source_name", "").lower()
                if s_name and any(tok in s_name for tok in query_tokens if len(tok) > 2):
                    target_source_id = c.get("source_id")
                    break

            if not target_source_id:
                # Default to the most recently uploaded document
                target_source_id = user_candidates[0].get("source_id")

            # Collect all chunks belonging to the active uploaded document
            doc_chunks = [c for c in user_candidates if c.get("source_id") == target_source_id]

            # Sort strictly by chunk_index ascending so reading flow (Page 1 -> Page 2 -> ...) is preserved
            doc_chunks.sort(key=lambda x: x.get("chunk_index", 0))

            for c in doc_chunks:
                searchable_text = f"{c.get('source_name', '')} {c.get('content', '')}"
                match_score = _compute_relevance_score(query_tokens, searchable_text)
                user_scored.append({
                    "chunk_id": c.get("chunk_id"),
                    "source_id": c.get("source_id"),
                    "source_name": c.get("source_name", "Document"),
                    "content": c.get("content", ""),
                    "chunk_index": c.get("chunk_index", 0),
                    "score": 1.0 + match_score,  # Keep every chunk of active document with keyword boost
                    "is_user_document": True,
                })

        scored_chunks.extend(user_scored)

        # 2. Fetch general website knowledge chunks
        kb_filter: Dict[str, Any] = {
            "website_id": website_id,
            "tenant_id": tenant_id,
            "$or": [
                {"is_user_document": False},
                {"is_user_document": {"$exists": False}},
            ],
        }
        kb_candidates = list(chunks_col.find(kb_filter).limit(100))
        for c in kb_candidates:
            searchable_text = f"{c.get('source_name', '')} {c.get('content', '')}"
            score = _compute_relevance_score(query_tokens, searchable_text)
            if score > 0.05:
                scored_chunks.append({
                    "chunk_id": c.get("chunk_id"),
                    "source_id": c.get("source_id"),
                    "source_name": c.get("source_name", "Knowledge Base"),
                    "content": c.get("content", ""),
                    "chunk_index": c.get("chunk_index", 0),
                    "score": score,
                    "is_user_document": False,
                })

        # Separate user uploaded document chunks and knowledge chunks
        user_chunks = [c for c in scored_chunks if c.get("is_user_document")]
        kb_chunks = [c for c in scored_chunks if not c.get("is_user_document")]

        # For uploaded user documents, sort strictly by chunk_index ascending (Page 1 -> Page 2 -> ...)
        # so the LLM reads the receipt/invoice from top to bottom in natural sequential order
        user_chunks.sort(key=lambda x: x.get("chunk_index", 0))
        kb_chunks.sort(key=lambda x: (-x["score"], x.get("chunk_index", 0)))

        # When an uploaded document is present, return all its chunks (up to 30) so multi-page bills are 100% complete
        if user_chunks:
            return user_chunks[:30]
        return kb_chunks[:top_k]

    def list_knowledge_documents(self, website_id: str) -> List[Dict[str, Any]]:
        """List all permanent knowledge base sources for this website."""
        know_col = get_knowledge_sources_collection()
        if know_col is None:
            return []
        docs = list(know_col.find({"website_id": website_id}, {"_id": 0}).sort("created_at", -1))
        return docs

    def delete_document(self, document_id: str) -> bool:
        """Delete document metadata and all its indexed chunks."""
        chunks_col = get_document_chunks_collection()
        know_col = get_knowledge_sources_collection()
        user_docs_col = get_user_documents_collection()

        deleted = False
        if chunks_col is not None:
            res = chunks_col.delete_many({"source_id": document_id})
            if res.deleted_count > 0:
                deleted = True
        if know_col is not None:
            res = know_col.delete_many({"source_id": document_id})
            if res.deleted_count > 0:
                deleted = True
        if user_docs_col is not None:
            res = user_docs_col.delete_many({"document_id": document_id})
            if res.deleted_count > 0:
                deleted = True
        return deleted


rag_service = RAGService()
