import copy
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from core.config import settings

logger = logging.getLogger(__name__)

_mongo_client: Optional[MongoClient] = None


def get_mongo_client() -> Optional[MongoClient]:
    """Retrieve or initialize the singleton MongoClient instance."""
    global _mongo_client
    if not settings.MONGODB_ENABLED:
        return None

    if _mongo_client is None:
        try:
            _mongo_client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000,
                socketTimeoutMS=5000,
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize MongoClient: {exc}")
            return None

    return _mongo_client


def get_receipt_collection() -> Optional[Collection]:
    """Get the target collection for receipt extractions."""
    client = get_mongo_client()
    if client is None:
        return None

    try:
        # Check if database is specified in URI, otherwise use configured default
        try:
            db = client.get_default_database()
        except Exception:
            db = client[settings.MONGODB_DB_NAME]

        return db[settings.MONGODB_COLLECTION]
    except Exception as exc:
        logger.warning(f"Failed to access MongoDB database/collection: {exc}")
        return None


def find_extraction_by_invoice_number(invoice_number: str) -> Optional[Dict[str, Any]]:
    """
    Search MongoDB for an existing extraction record by invoice/receipt number.

    Performs a case-insensitive exact match and checks both string and integer representations.
    Returns the matched document dict (with stringified '_id') if found, or None.
    """
    if not settings.MONGODB_ENABLED or not invoice_number:
        return None

    clean_inv = str(invoice_number).strip()
    if not clean_inv:
        return None

    collection = get_receipt_collection()
    if collection is None:
        return None

    try:
        escaped = re.escape(clean_inv)
        or_conditions: List[Dict[str, Any]] = [
            {"data.invoice_number": {"$regex": f"^{escaped}$", "$options": "i"}},
            {"data.receipt_number": {"$regex": f"^{escaped}$", "$options": "i"}},
            {"invoice_number": {"$regex": f"^{escaped}$", "$options": "i"}},
            {"receipt_number": {"$regex": f"^{escaped}$", "$options": "i"}},
        ]
        if clean_inv.isdigit():
            int_val = int(clean_inv)
            or_conditions.extend([
                {"data.invoice_number": int_val},
                {"data.receipt_number": int_val},
                {"invoice_number": int_val},
                {"receipt_number": int_val},
            ])

        doc = collection.find_one({"$or": or_conditions})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None
    except Exception as exc:
        logger.warning(f"Error querying existing invoice number '{clean_inv}' in MongoDB: {exc}")
        return None


def save_extraction_to_mongodb(response_payload: Dict[str, Any]) -> Optional[str]:
    """
    Persist the receipt extraction JSON response into the MongoDB Receipt_Extraction collection
    ONLY if not already present based on invoice number.

    If an extraction with the same invoice number already exists in MongoDB:
      - Does NOT insert a duplicate document into the database.
      - Sets response_payload["is_duplicate"] = True (if payload is a dict).
      - Returns the existing document's ID string.

    If no matching invoice is found (or no invoice number is present):
      - Inserts the new extraction document.
      - Sets response_payload["is_duplicate"] = False (if payload is a dict).
      - Returns the newly inserted document's ID string.

    Returns None if MongoDB is unavailable or disabled.
    """
    if not settings.MONGODB_ENABLED:
        return None

    try:
        collection = get_receipt_collection()
        if collection is None:
            logger.warning("MongoDB collection is unavailable; skipping storage.")
            return None

        # 1. Locate invoice / receipt number from the payload
        data = response_payload.get("data", {}) if isinstance(response_payload.get("data"), dict) else {}
        invoice_num = (
            data.get("invoice_number")
            or data.get("receipt_number")
            or response_payload.get("invoice_number")
            or response_payload.get("receipt_number")
        )

        doc_to_save = copy.deepcopy(response_payload)
        now_iso = datetime.now(timezone.utc).isoformat()

        # 2. Check if already present in MongoDB using the invoice number
        if invoice_num:
            clean_inv = str(invoice_num).strip()
            if clean_inv:
                existing_doc = find_extraction_by_invoice_number(clean_inv)
                if existing_doc:
                    existing_id = existing_doc["_id"]
                    doc_to_save["_id"] = existing_id
                    doc_to_save["stored_at"] = existing_doc.get("stored_at", now_iso)
                    doc_to_save["updated_at"] = now_iso
                    collection.replace_one({"_id": existing_id}, doc_to_save, upsert=True)
                    str_id = str(existing_id)
                    logger.info(
                        f"Invoice number '{clean_inv}' updated in MongoDB with ID {str_id}."
                    )
                    if isinstance(response_payload, dict):
                        response_payload["is_duplicate"] = True
                    return str_id

        # 3. Not found or no invoice number — store in database as normal
        doc_to_save["stored_at"] = now_iso
        insert_result = collection.insert_one(doc_to_save)
        doc_id = str(insert_result.inserted_id)
        logger.info(f"Receipt extraction stored in MongoDB with ID: {doc_id}")
        if isinstance(response_payload, dict):
            response_payload["is_duplicate"] = False
        return doc_id

    except (ServerSelectionTimeoutError, PyMongoError) as exc:
        logger.warning(f"MongoDB storage failed (database unreachable or error): {exc}")
        return None
    except Exception as exc:
        logger.warning(f"Unexpected error while storing receipt in MongoDB: {exc}")
        return None


def get_stored_extractions(limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    """Fetch stored receipt extraction records from MongoDB."""
    collection = get_receipt_collection()
    if collection is None:
        return []

    try:
        cursor = collection.find().sort("_id", -1).skip(skip).limit(limit)
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results
    except Exception as exc:
        logger.warning(f"Failed to query stored receipt extractions: {exc}")
        return []


def get_stored_extraction_by_id(doc_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single stored extraction by document ID."""
    collection = get_receipt_collection()
    if collection is None:
        return None

    try:
        if not ObjectId.is_valid(doc_id):
            return None
        doc = collection.find_one({"_id": ObjectId(doc_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as exc:
        logger.warning(f"Failed to query receipt extraction {doc_id}: {exc}")
        return None


def check_mongo_connection() -> Dict[str, Any]:
    """Check connectivity to MongoDB and return diagnostic status."""
    if not settings.MONGODB_ENABLED:
        return {"status": "disabled"}

    try:
        client = get_mongo_client()
        if client is None:
            return {"status": "unreachable", "error": "Client not initialized"}
        client.admin.command("ping")
        return {
            "status": "connected",
            "uri": settings.MONGODB_URI,
            "database": settings.MONGODB_DB_NAME,
            "collection": settings.MONGODB_COLLECTION,
        }
    except Exception as exc:
        return {"status": "disconnected", "error": str(exc)}
