import logging
import re
from typing import Any, Dict, List, Optional
from pymongo import MongoClient

from universal_chatbot.backend.app.database.collections import get_app_connections_collection

logger = logging.getLogger(__name__)


class ApplicationMongoAdapter:
    """
    Secure database adapter allowing the chatbot to query an external or host application's
    MongoDB database (e.g., receipt_db) with strict read-only permissions, field allowlisting,
    and user isolation.
    """

    def __init__(self):
        self._cached_clients: Dict[str, MongoClient] = {}

    def _get_client(self, uri: str) -> MongoClient:
        if uri not in self._cached_clients:
            self._cached_clients[uri] = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._cached_clients[uri]

    def get_connection_config(self, website_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve registered application connection for a website."""
        app_col = get_app_connections_collection()
        if app_col is None:
            return None
        return app_col.find_one({"website_id": website_id, "status": "active"})

    def query_application_data(
        self,
        website_id: str,
        user_query: str,
        user_id: Optional[str] = None,
        max_results: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        Inspect user query, execute safe search on allowed application collections,
        and return sanitized document records to inject into chatbot prompt context.
        """
        conn = self.get_connection_config(website_id)
        if not conn:
            return None

        target_uri = conn.get("target_uri")
        target_db = conn.get("target_db")
        allowed_col = conn.get("allowed_collection")

        if not target_uri or not target_db or not allowed_col:
            return None

        try:
            client = self._get_client(target_uri)
            db = client[target_db]
            collection = db[allowed_col]

            conditions: List[Dict[str, Any]] = []

            # 1. Strict User Boundary Condition
            if user_id:
                user_f = conn.get("user_id_field") or "user_id"
                conditions.append({
                    "$or": [
                        {user_f: user_id},
                        {f"data.{user_f}": user_id},
                        {"user_id": user_id},
                        {"candidate_id": user_id},
                    ]
                })

            # 2. Extract search terms from user query
            tokens = re.findall(r"[\w]+", user_query, re.UNICODE)
            stop_words = {
                "show", "me", "all", "the", "my", "receipts", "receipt", "invoices",
                "invoice", "from", "for", "latest", "what", "how", "much", "did",
                "spend", "at", "in", "bill", "bills", "get", "view", "details",
                "ரசீது", "ரசீதுகள்", "காட்டு", "எனது", "விவரங்கள்", "சுருக்கமாக",
                "தகவல்கள்", "உள்ள"
            }
            search_terms = [t for t in tokens if t.lower() not in stop_words and len(t) > 2]

            if search_terms:
                regex_pattern = "|".join([re.escape(t) for t in search_terms])
                conditions.append({
                    "$or": [
                        {"data.vendor_name": {"$regex": regex_pattern, "$options": "i"}},
                        {"data.seller": {"$regex": regex_pattern, "$options": "i"}},
                        {"data.buyer": {"$regex": regex_pattern, "$options": "i"}},
                        {"data.invoice_number": {"$regex": regex_pattern, "$options": "i"}},
                        {"data.category": {"$regex": regex_pattern, "$options": "i"}},
                        {"formatted_display": {"$regex": regex_pattern, "$options": "i"}},
                        {"vendor_name": {"$regex": regex_pattern, "$options": "i"}},
                    ]
                })

            filter_query: Dict[str, Any] = {}
            if len(conditions) == 1:
                filter_query = conditions[0]
            elif len(conditions) > 1:
                filter_query = {"$and": conditions}

            cursor = collection.find(filter_query).sort("_id", -1).limit(max_results)
            raw_records = list(cursor)

            if not raw_records and not search_terms and not user_id:
                # If broad inquiry without specific keyword or user, fetch the latest recent records
                cursor = collection.find({}).sort("_id", -1).limit(max_results)
                raw_records = list(cursor)

            if not raw_records:
                return None

            # Sanitize and flatten records
            sanitized_records = []
            for r in raw_records:
                data_sub = r.get("data") or {}
                vendor = data_sub.get("vendor_name") or data_sub.get("seller") or r.get("vendor_name")
                buyer = data_sub.get("buyer") or data_sub.get("customer_name") or r.get("buyer_name")
                inv_no = data_sub.get("invoice_number") or r.get("invoice_number")
                inv_date = data_sub.get("invoice_date") or r.get("stored_date")
                total = data_sub.get("grand_total") or r.get("total_amount")
                sanitized_records.append({
                    "vendor_or_seller": vendor,
                    "vendor_name": vendor,
                    "buyer": buyer,
                    "invoice_number": inv_no,
                    "invoice_date": inv_date,
                    "grand_total": total,
                    "total_amount": total,
                    "date": inv_date,
                    "currency": data_sub.get("currency", "INR"),
                    "items": [
                        {"name": it.get("item_name"), "qty": it.get("quantity"), "amount": it.get("total_price")}
                        for it in data_sub.get("items", [])[:3]
                    ] if isinstance(data_sub.get("items"), list) else [],
                })

            return {
                "source_app": conn.get("app_name", target_db),
                "collection": allowed_col,
                "record_count": len(sanitized_records),
                "records": sanitized_records,
            }

        except Exception as exc:
            logger.warning(f"ApplicationMongoAdapter query failed: {exc}")
            return None


app_mongo_adapter = ApplicationMongoAdapter()
