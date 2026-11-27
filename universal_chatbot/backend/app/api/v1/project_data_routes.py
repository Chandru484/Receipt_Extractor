import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from universal_chatbot.backend.app.database.collections import get_collection
from universal_chatbot.backend.app.database.mongodb import get_project_db
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Universal Project Data Management"])

PLATFORM_SYSTEM_COLLECTIONS = {
    "conversations",
    "messages",
    "visitor_sessions",
    "document_chunks",
    "knowledge_sources",
    "support_handoffs",
    "analytics_events",
    "admins",
    "tenants",
    "websites",
    "app_connections",
    "system.indexes",
}

COMMON_USER_FIELDS = [
    "user_id",
    "customer_id",
    "patient_id",
    "employee_id",
    "client_id",
    "member_id",
    "student_id",
    "email",
    "candidate_id",
]


@router.get("/{project_id}/tables", summary="List all data tables in project database")
def list_project_tables(project_id: str):
    """
    List all application data tables/collections present in this project's dedicated MongoDB database.
    """
    db = get_project_db(project_id)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB is not connected",
        )
    col_names = [c for c in db.list_collection_names() if c not in PLATFORM_SYSTEM_COLLECTIONS]
    return {
        "project_id": project_id,
        "database": f"project_{re.sub(r'[^\w\-]', '_', str(project_id).strip().lower())}_db",
        "tables": col_names,
        "count": len(col_names),
    }


@router.post("/{project_id}/tables/{table_name}", summary="Insert or update data in any project table")
async def insert_project_table_data(project_id: str, table_name: str, request: Request):
    """
    Universal API to insert or update any structured business record(s) into this project's database table.
    Works for ANY project entity: orders, appointments, tickets, leaves, products, patients, etc.
    """
    clean_table = re.sub(r"[^\w\-]", "_", str(table_name).strip().lower())
    if clean_table in PLATFORM_SYSTEM_COLLECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table name '{table_name}' is a reserved platform collection",
        )

    col = get_collection(clean_table, website_id=project_id)
    if col is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB is not connected",
        )

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON body: {exc}",
        )

    now_str = get_ist_now_str()
    records = body if isinstance(body, list) else [body]
    inserted_ids = []

    for r in records:
        if not isinstance(r, dict):
            continue
        doc = dict(r)
        # Find or generate an ID for this record
        doc_id = (
            doc.get("id")
            or doc.get(f"{clean_table.rstrip('s')}_id")
            or doc.get("order_id")
            or doc.get("ticket_id")
            or doc.get("appointment_id")
            or doc.get("leave_id")
            or f"{clean_table.upper()[:3]}-{uuid.uuid4().hex[:8].upper()}"
        )
        doc["id"] = doc_id
        if f"{clean_table.rstrip('s')}_id" not in doc:
            doc[f"{clean_table.rstrip('s')}_id"] = doc_id

        if "created_at" not in doc:
            doc["created_at"] = now_str
        doc["updated_at"] = now_str

        # Upsert document by id or specific entity ID
        id_field = f"{clean_table.rstrip('s')}_id"
        col.update_one(
            {"$or": [{"id": doc_id}, {id_field: doc_id}]},
            {"$set": doc},
            upsert=True,
        )
        inserted_ids.append(doc_id)

    return {
        "status": "success",
        "project_id": project_id,
        "table": clean_table,
        "count": len(inserted_ids),
        "record_ids": inserted_ids,
    }


@router.get("/{project_id}/tables/{table_name}", summary="Query records from any project table")
def query_project_table_data(
    project_id: str,
    table_name: str,
    user_id: Optional[str] = Query(None, description="Optional filter by user ID"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """
    Universal API to retrieve records from any project table, with optional user boundary isolation.
    """
    clean_table = re.sub(r"[^\w\-]", "_", str(table_name).strip().lower())
    col = get_collection(clean_table, website_id=project_id)
    if col is None:
        return {"project_id": project_id, "table": clean_table, "count": 0, "records": []}

    query: Dict[str, Any] = {}
    if user_id:
        query = {"$or": [{uf: user_id} for uf in COMMON_USER_FIELDS]}

    cursor = col.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    records = list(cursor)

    return {
        "project_id": project_id,
        "table": clean_table,
        "count": len(records),
        "records": records,
    }


@router.delete("/{project_id}/tables/{table_name}/{record_id}", summary="Delete a record from project table")
def delete_project_table_record(project_id: str, table_name: str, record_id: str):
    """
    Delete a specific record from any project table.
    """
    clean_table = re.sub(r"[^\w\-]", "_", str(table_name).strip().lower())
    col = get_collection(clean_table, website_id=project_id)
    if col is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB is not connected",
        )

    id_field = f"{clean_table.rstrip('s')}_id"
    res = col.delete_one({"$or": [{"id": record_id}, {id_field: record_id}]})
    if res.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record '{record_id}' not found in table '{clean_table}'",
        )
    return {"status": "deleted", "project_id": project_id, "table": clean_table, "record_id": record_id}


# --- Backward Compatibility Aliases for Orders ---
@router.post("/{project_id}/orders", summary="Insert order (legacy alias for /tables/orders)")
async def legacy_create_project_order(project_id: str, request: Request):
    return await insert_project_table_data(project_id, "orders", request)


@router.get("/{project_id}/orders", summary="List orders (legacy alias for /tables/orders)")
def legacy_list_project_orders(
    project_id: str,
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return query_project_table_data(project_id, "orders", user_id=user_id, limit=limit)


@router.delete("/{project_id}/orders/{order_id}", summary="Delete order (legacy alias for /tables/orders/{id})")
def legacy_delete_project_order(project_id: str, order_id: str):
    return delete_project_table_record(project_id, "orders", record_id=order_id)
