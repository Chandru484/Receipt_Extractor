import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from universal_chatbot.backend.app.database.collections import get_orders_collection
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Project Data Management"])


class OrderItem(BaseModel):
    name: str
    qty: int = 1
    amount: float = 0.0


class CreateOrderRequest(BaseModel):
    order_id: Optional[str] = None
    user_id: str
    customer_name: Optional[str] = None
    vendor: str = "Store"
    amount: float
    status: str = "Completed"
    items: List[OrderItem] = []
    date: Optional[str] = None
    category: Optional[str] = None


@router.post("/{project_id}/orders", summary="Insert order into project database")
def create_project_order(project_id: str, payload: CreateOrderRequest):
    """
    Store an order record strictly inside this project's isolated MongoDB database.
    (e.g., project_{project_id}_db.orders)
    """
    col = get_orders_collection(website_id=project_id)
    if col is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB is not connected",
        )

    order_id = payload.order_id or f"ORD-{uuid.uuid4().hex[:8].upper()}"
    now_str = get_ist_now_str()
    order_doc = {
        "order_id": order_id,
        "user_id": payload.user_id,
        "customer_name": payload.customer_name or payload.user_id,
        "vendor": payload.vendor,
        "vendor_name": payload.vendor,
        "amount": float(payload.amount),
        "grand_total": float(payload.amount),
        "status": payload.status,
        "items": [it.model_dump() for it in payload.items],
        "date": payload.date or now_str.split(" ")[0],
        "created_at": now_str,
        "category": payload.category or "General",
    }
    col.update_one({"order_id": order_id}, {"$set": order_doc}, upsert=True)
    return {"status": "success", "order_id": order_id, "order": order_doc}


@router.get("/{project_id}/orders", summary="List orders from project database")
def list_project_orders(
    project_id: str,
    user_id: Optional[str] = Query(None, description="Filter by user_id"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Fetch order records strictly from this project's isolated MongoDB database.
    """
    col = get_orders_collection(website_id=project_id)
    if col is None:
        return {"orders": [], "count": 0}

    query: Dict[str, Any] = {}
    if user_id:
        query = {
            "$or": [
                {"user_id": user_id},
                {"customer_id": user_id},
                {"candidate_id": user_id},
            ]
        }

    docs = list(col.find(query, {"_id": 0}).sort("created_at", -1).limit(limit))
    return {"project_id": project_id, "orders": docs, "count": len(docs)}


@router.delete("/{project_id}/orders/{order_id}", summary="Delete order from project database")
def delete_project_order(project_id: str, order_id: str):
    """
    Remove an order from this project's database.
    """
    col = get_orders_collection(website_id=project_id)
    if col is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB is not connected",
        )
    res = col.delete_one({"order_id": order_id})
    if res.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found in project '{project_id}'",
        )
    return {"status": "deleted", "order_id": order_id}
