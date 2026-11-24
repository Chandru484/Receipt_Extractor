import copy
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from core.config import settings

logger = logging.getLogger(__name__)

# Indian Standard Time (IST, UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


def get_current_ist_datetime_str() -> str:
    """Return the current timestamp in Indian Standard Time (IST) in DD-MM-YYYY HH:MM:SS format."""
    return datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")


def get_current_ist_date_str() -> str:
    """Return the current date in Indian Standard Time (IST) in DD-MM-YYYY format."""
    return datetime.now(IST).strftime("%d-%m-%Y")


def format_to_ist_str(dt_val: Any) -> str:
    """Normalize a datetime object or ISO string into DD-MM-YYYY HH:MM:SS in Indian Standard Time (IST)."""
    if not dt_val:
        return get_current_ist_datetime_str()
    if isinstance(dt_val, str):
        # Already DD-MM-YYYY format
        if re.match(r"^\d{2}-\d{2}-\d{4}", dt_val):
            return dt_val
        try:
            parsed = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            return parsed.astimezone(IST).strftime("%d-%m-%Y %H:%M:%S")
        except Exception:
            return dt_val
    elif isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(IST).strftime("%d-%m-%Y %H:%M:%S")
    return str(dt_val)


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


def find_extraction_by_file_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    """
    Search MongoDB for an existing extraction record by file SHA-256 hash.

    Returns the matched document dict (with stringified '_id') if found, or None.
    """
    if not settings.MONGODB_ENABLED or not file_hash:
        return None

    clean_hash = str(file_hash).strip().lower()
    if not clean_hash:
        return None

    collection = get_receipt_collection()
    if collection is None:
        return None

    try:
        doc = collection.find_one({"file_hash": clean_hash})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None
    except Exception as exc:
        logger.warning(f"Error querying existing file hash '{clean_hash[:12]}...' in MongoDB: {exc}")
        return None


def find_extraction_by_invoice_and_vendor(
    invoice_number: str,
    vendor_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Search MongoDB for an existing extraction record by combining BOTH
    invoice/receipt number and vendor/seller name.

    - A single vendor can have multiple receipts with different invoice numbers.
    - Different vendors may issue receipts with identical invoice numbers (e.g. '1', '101', '3').
    - Matching on BOTH invoice number and vendor/seller name ensures:
        1. Accurate cache hits for the specific vendor.
        2. No cross-vendor collisions.
        3. Distinct storage for each receipt belonging to the same vendor.

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
        escaped_inv = re.escape(clean_inv)
        inv_conditions: List[Dict[str, Any]] = [
            {"data.invoice_number": {"$regex": f"^{escaped_inv}$", "$options": "i"}},
            {"data.receipt_number": {"$regex": f"^{escaped_inv}$", "$options": "i"}},
            {"invoice_number": {"$regex": f"^{escaped_inv}$", "$options": "i"}},
            {"receipt_number": {"$regex": f"^{escaped_inv}$", "$options": "i"}},
        ]
        if clean_inv.isdigit():
            int_val = int(clean_inv)
            inv_conditions.extend([
                {"data.invoice_number": int_val},
                {"data.receipt_number": int_val},
                {"invoice_number": int_val},
                {"receipt_number": int_val},
            ])

        clean_vendor = str(vendor_name).strip() if vendor_name else ""
        if clean_vendor:
            escaped_vendor = re.escape(clean_vendor)
            vendor_conditions: List[Dict[str, Any]] = [
                {"data.vendor_name": {"$regex": escaped_vendor, "$options": "i"}},
                {"data.seller_name": {"$regex": escaped_vendor, "$options": "i"}},
                {"data.seller": {"$regex": escaped_vendor, "$options": "i"}},
                {"data.vendor": {"$regex": escaped_vendor, "$options": "i"}},
                {"vendor_name": {"$regex": escaped_vendor, "$options": "i"}},
                {"seller_name": {"$regex": escaped_vendor, "$options": "i"}},
                {"formatted_display": {"$regex": escaped_vendor, "$options": "i"}},
            ]
            query = {
                "$and": [
                    {"$or": inv_conditions},
                    {"$or": vendor_conditions}
                ]
            }
        else:
            query = {"$or": inv_conditions}

        doc = collection.find_one(query)
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None
    except Exception as exc:
        logger.warning(
            f"Error querying invoice '{clean_inv}' for vendor '{vendor_name or 'any'}' in MongoDB: {exc}"
        )
        return None


def find_extraction_by_invoice_number(
    invoice_number: str,
    vendor_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Search MongoDB for an existing extraction record by invoice/receipt number and optional vendor.
    Delegates to find_extraction_by_invoice_and_vendor.
    """
    return find_extraction_by_invoice_and_vendor(invoice_number=invoice_number, vendor_name=vendor_name)


def save_extraction_to_mongodb(
    response_payload: Dict[str, Any],
    file_hash: Optional[str] = None,
    file_name: Optional[str] = None,
    vendor_name: Optional[str] = None,
    invoice_number: Optional[str] = None
) -> Optional[str]:
    """
    Persist the receipt extraction JSON response into the MongoDB Receipt_Extraction collection
    ONLY if not already present based on file hash OR (invoice number AND vendor/seller name).

    If an extraction with the same file hash OR (same invoice number and vendor) already exists:
      - Does NOT insert a duplicate document into the database.
      - Updates the existing document in place using its BSON ObjectId.
      - Sets response_payload["is_duplicate"] = True (if payload is a dict).
      - Returns the existing document's ID string.

    If the same vendor has a NEW invoice number (or a different vendor has the same invoice number):
      - Inserts the new extraction document without collision.
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

        # Clean file hash and file name
        resolved_hash = (
            file_hash
            or response_payload.get("file_hash")
        )
        if resolved_hash:
            resolved_hash = str(resolved_hash).strip().lower()

        resolved_name = (
            file_name
            or response_payload.get("file_name")
        )

        # 1. Locate invoice number and vendor/seller name from payload
        data = response_payload.get("data", {}) if isinstance(response_payload.get("data"), dict) else {}
        resolved_inv = (
            invoice_number
            or data.get("invoice_number")
            or data.get("receipt_number")
            or response_payload.get("invoice_number")
            or response_payload.get("receipt_number")
        )
        resolved_vendor = (
            vendor_name
            or data.get("vendor_name")
            or data.get("seller_name")
            or data.get("seller")
            or data.get("vendor")
            or response_payload.get("vendor_name")
            or response_payload.get("seller_name")
        )

        doc_to_save = copy.deepcopy(response_payload)
        now_ist_str = get_current_ist_datetime_str()
        now_ist_date = get_current_ist_date_str()

        # 2. Check if already present by file SHA-256 hash (exact duplicate file)
        if resolved_hash:
            existing_doc = find_extraction_by_file_hash(resolved_hash)
            if existing_doc:
                existing_id = existing_doc["_id"]
                mongo_id = ObjectId(existing_id) if ObjectId.is_valid(str(existing_id)) else existing_id
                doc_to_save["_id"] = mongo_id
                doc_to_save["file_hash"] = resolved_hash
                if resolved_name:
                    doc_to_save["file_name"] = resolved_name
                doc_to_save["stored_at"] = format_to_ist_str(existing_doc.get("stored_at", now_ist_str))
                doc_to_save["stored_date"] = existing_doc.get("stored_date", now_ist_date)
                doc_to_save["updated_at"] = now_ist_str
                doc_to_save["updated_date"] = now_ist_date
                collection.replace_one({"_id": mongo_id}, doc_to_save, upsert=True)
                str_id = str(existing_id)
                logger.info(
                    f"File hash '{resolved_hash[:12]}...' updated in MongoDB with ID {str_id} at {now_ist_str} IST."
                )
                if isinstance(response_payload, dict):
                    response_payload["is_duplicate"] = True
                    response_payload["document_id"] = str_id
                return str_id

        # 3. Check if already present by combining BOTH invoice number AND vendor name
        if resolved_inv:
            clean_inv = str(resolved_inv).strip()
            clean_vendor = str(resolved_vendor).strip() if resolved_vendor else None
            if clean_inv:
                existing_doc = find_extraction_by_invoice_and_vendor(clean_inv, clean_vendor)
                if existing_doc:
                    existing_id = existing_doc["_id"]
                    mongo_id = ObjectId(existing_id) if ObjectId.is_valid(str(existing_id)) else existing_id
                    doc_to_save["_id"] = mongo_id
                    if resolved_hash:
                        doc_to_save["file_hash"] = resolved_hash
                    if resolved_name:
                        doc_to_save["file_name"] = resolved_name
                    doc_to_save["stored_at"] = format_to_ist_str(existing_doc.get("stored_at", now_ist_str))
                    doc_to_save["stored_date"] = existing_doc.get("stored_date", now_ist_date)
                    doc_to_save["updated_at"] = now_ist_str
                    doc_to_save["updated_date"] = now_ist_date
                    collection.replace_one({"_id": mongo_id}, doc_to_save, upsert=True)
                    str_id = str(existing_id)
                    logger.info(
                        f"Invoice '{clean_inv}' for vendor '{clean_vendor or 'Unknown'}' updated in MongoDB with ID {str_id} at {now_ist_str} IST."
                    )
                    if isinstance(response_payload, dict):
                        response_payload["is_duplicate"] = True
                        response_payload["document_id"] = str_id
                    return str_id

        # 4. Not found — store in database as new extraction
        if resolved_hash:
            doc_to_save["file_hash"] = resolved_hash
        if resolved_name:
            doc_to_save["file_name"] = resolved_name
        doc_to_save["stored_at"] = now_ist_str
        doc_to_save["stored_date"] = now_ist_date
        doc_to_save["updated_at"] = now_ist_str
        doc_to_save["updated_date"] = now_ist_date
        insert_result = collection.insert_one(doc_to_save)
        doc_id = str(insert_result.inserted_id)
        logger.info(f"Receipt extraction stored in MongoDB with ID: {doc_id} at {now_ist_str} IST")
        if isinstance(response_payload, dict):
            response_payload["is_duplicate"] = False
            response_payload["document_id"] = doc_id
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
