import copy
import logging
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


def save_extraction_to_mongodb(response_payload: Dict[str, Any]) -> Optional[str]:
    """
    Persist the receipt extraction JSON response into the MongoDB Receipt_Extraction collection.
    
    Returns the inserted document ID string if successful, or None if MongoDB is unavailable.
    Does not raise exceptions to ensure API extraction never fails due to DB connectivity.
    """
    if not settings.MONGODB_ENABLED:
        return None

    try:
        collection = get_receipt_collection()
        if collection is None:
            logger.warning("MongoDB collection is unavailable; skipping storage.")
            return None

        # Make a deep copy to avoid mutating the original response dictionary
        doc_to_save = copy.deepcopy(response_payload)
        
        # Attach ISO timestamp for auditing and query convenience
        doc_to_save["stored_at"] = datetime.now(timezone.utc).isoformat()

        insert_result = collection.insert_one(doc_to_save)
        doc_id = str(insert_result.inserted_id)
        logger.info(f"Receipt extraction stored in MongoDB with ID: {doc_id}")
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
