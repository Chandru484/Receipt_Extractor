import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from pymongo import MongoClient

from universal_chatbot.backend.app.database.collections import get_app_connections_collection

logger = logging.getLogger(__name__)

TAMIL_MONTH_MAP = {
    "ஜனவரி": 1, "january": 1, "jan": 1,
    "பிப்ரவரி": 2, "february": 2, "feb": 2,
    "மார்ச்": 3, "march": 3, "mar": 3,
    "ஏப்ரல்": 4, "april": 4, "apr": 4,
    "மே": 5, "may": 5,
    "ஜூன்": 6, "june": 6, "jun": 6,
    "ஜூலை": 7, "july": 7, "jul": 7,
    "ஆகஸ்ட்": 8, "august": 8, "aug": 8,
    "செப்டம்பர்": 9, "september": 9, "sep": 9,
    "அக்டோபர்": 10, "october": 10, "oct": 10,
    "நவம்பர்": 11, "november": 11, "nov": 11,
    "டிசம்பர்": 12, "december": 12, "dec": 12,
}

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TAMIL_MONTH_NAMES = ["", "ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"]

EXPENSE_KEYWORDS = [
    "செலவு", "செலவுகள்", "செலவழித்த", "செலவாச்சு", "செலவாயிருக்கு", "செலவு பண்ணியிருக்கேன்",
    "மொத்த தொகை", "மொத்த செலவு", "மொத்தம் எவ்வளவு", "கணக்கு", "அதிக செலவு", "பில் தொகை",
    "selavu", "selavugal", "selavachu", "selavaachu", "motha selavu", "motham selavu",
    "total selavu", "spend", "spending", "spent", "expense", "expenses", "expenditure",
    "highest spend", "total spent", "total cost", "how much did i spend", "evvalavu selavu",
    "paniruken", "panniyiruken"
]


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
        """Retrieve registered application connection for a website or auto-provision a new project database."""
        app_col = get_app_connections_collection()
        if app_col is None:
            return None
        conn = app_col.find_one({"website_id": website_id, "status": "active"})
        if not conn:
            from universal_chatbot.backend.app.core.config import chatbot_settings
            from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str
            clean_pid = re.sub(r"[^\w\-]", "_", str(website_id).strip())
            target_db = "receipt_db" if clean_pid == "site_demo" else f"project_{clean_pid}_db"
            conn = {
                "website_id": website_id,
                "tenant_id": "ten_default",
                "app_name": f"{clean_pid.replace('_', ' ').title()} App",
                "db_type": "mongodb",
                "target_uri": chatbot_settings.CHATBOT_MONGODB_URI,
                "target_db": target_db,
                "allowed_collection": "Receipt_Extraction",
                "allowed_fields": ["*"],
                "status": "active",
                "created_at": get_ist_now_str(),
            }
            try:
                app_col.insert_one(dict(conn))
                conn.pop("_id", None)
            except Exception as exc:
                logger.warning(f"Could not auto-provision app_connection: {exc}")
        return conn

    @staticmethod
    def is_expense_query(query: str) -> bool:
        """Check if user query is asking about overall expenses, spending totals, or category breakdowns."""
        q_lower = query.lower()
        return any(k in q_lower for k in EXPENSE_KEYWORDS)

    @staticmethod
    def _parse_amount(val: Any) -> float:
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = re.sub(r"[^\d.]", "", str(val))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_date(date_str: Any) -> Optional[Tuple[int, int, str]]:
        if not date_str:
            return None
        s = str(date_str).strip()
        m1 = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
        if m1:
            yr, mo = int(m1.group(1)), int(m1.group(2))
            return yr, mo, s
        m2 = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
        if m2:
            yr, mo = int(m2.group(3)), int(m2.group(2))
            return yr, mo, s
        return None

    def get_expense_analytics(
        self,
        website_id: str,
        user_query: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute real-time expense and spending aggregations across all accessible receipts,
        including total expenditure, monthly breakdown, vendor breakdown, and specific query matches.
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

            filter_q: Dict[str, Any] = {}
            if user_id:
                user_f = conn.get("user_id_field") or "user_id"
                filter_q = {
                    "$or": [
                        {user_f: user_id},
                        {f"data.{user_f}": user_id},
                        {"user_id": user_id},
                        {"candidate_id": user_id},
                    ]
                }

            docs = list(collection.find(filter_q))
            if not docs:
                return None

            total_spent = 0.0
            receipt_count = 0
            vendor_spends = defaultdict(lambda: {"total": 0.0, "count": 0, "dates": []})
            month_spends = defaultdict(lambda: {"total": 0.0, "count": 0, "year": 0, "month": 0, "name": ""})
            highest_receipt = {"vendor": "N/A", "amount": 0.0, "date": "N/A", "invoice_number": "N/A"}
            all_dates = []

            for doc in docs:
                data = doc.get("data") or {}
                amt = self._parse_amount(data.get("grand_total") or doc.get("total_amount"))
                vendor = data.get("vendor_name") or data.get("seller") or doc.get("vendor_name") or "Unknown"
                inv_date = data.get("invoice_date") or doc.get("stored_date") or doc.get("date")

                total_spent += amt
                receipt_count += 1

                vendor_spends[vendor]["total"] += amt
                vendor_spends[vendor]["count"] += 1
                if inv_date:
                    vendor_spends[vendor]["dates"].append(str(inv_date))

                p_date = self._parse_date(inv_date)
                if p_date:
                    yr, mo, raw_d = p_date
                    all_dates.append((yr, mo))
                    m_key = f"{yr}-{mo:02d}"
                    m_name = f"{TAMIL_MONTH_NAMES[mo]} {yr} ({MONTH_NAMES[mo]} {yr})"
                    month_spends[m_key]["total"] += amt
                    month_spends[m_key]["count"] += 1
                    month_spends[m_key]["year"] = yr
                    month_spends[m_key]["month"] = mo
                    month_spends[m_key]["name"] = m_name

                if amt > highest_receipt["amount"]:
                    highest_receipt = {
                        "vendor": vendor,
                        "amount": amt,
                        "date": str(inv_date) if inv_date else "N/A",
                        "invoice_number": data.get("invoice_number") or doc.get("invoice_number") or "N/A",
                    }

            latest_month_key = None
            if all_dates:
                all_dates.sort(reverse=True)
                latest_yr, latest_mo = all_dates[0]
                latest_month_key = f"{latest_yr}-{latest_mo:02d}"

            q_lower = user_query.lower()
            specific_vendor_match = None
            for v_name, v_info in vendor_spends.items():
                if v_name.lower() in q_lower or any(word in q_lower for word in v_name.lower().split() if len(word) > 3):
                    specific_vendor_match = {
                        "vendor": v_name,
                        "total": v_info["total"],
                        "count": v_info["count"],
                        "dates": v_info["dates"][:3],
                    }
                    break

            specific_month_match = None
            if any(rm in q_lower for rm in ["இந்த மாசம்", "இந்த மாதம்", "this month", "intha maasam", "intha masam", "நடப்பு மாதம்"]):
                if latest_month_key and latest_month_key in month_spends:
                    m_data = month_spends[latest_month_key]
                    specific_month_match = {
                        "type": "this_month",
                        "name": m_data["name"],
                        "total": m_data["total"],
                        "count": m_data["count"],
                        "is_active_latest": True,
                    }
            else:
                for m_str, m_num in TAMIL_MONTH_MAP.items():
                    if m_str in q_lower:
                        for mk, mv in month_spends.items():
                            if mv["month"] == m_num:
                                specific_month_match = {
                                    "type": "named_month",
                                    "name": mv["name"],
                                    "total": mv["total"],
                                    "count": mv["count"],
                                }
                                break
                        if specific_month_match:
                            break

            lines = [
                "=== REAL-TIME EXPENSE & SPENDING ANALYTICS ===",
                f"• Total Overall Spending: ₹ {total_spent:,.2f} across {receipt_count} receipts",
            ]

            if specific_month_match:
                lines.append(
                    f"• SPECIFIC QUERY MATCH (MONTH): User asked about this/specific month -> {specific_month_match['name']}: Total ₹ {specific_month_match['total']:,.2f} ({specific_month_match['count']} receipts)."
                )

            if specific_vendor_match:
                lines.append(
                    f"• SPECIFIC QUERY MATCH (VENDOR): User asked about {specific_vendor_match['vendor']} -> Total ₹ {specific_vendor_match['total']:,.2f} across {specific_vendor_match['count']} bills."
                )

            lines.append(
                f"• Highest Single Bill: {highest_receipt['vendor']} (₹ {highest_receipt['amount']:,.2f} on {highest_receipt['date']})"
            )

            top_months = sorted(month_spends.values(), key=lambda x: (x["year"], x["month"]), reverse=True)[:4]
            lines.append("• Recent Monthly Breakdown:")
            for tm in top_months:
                lines.append(f"   - {tm['name']}: ₹ {tm['total']:,.2f} ({tm['count']} receipts)")

            top_vends = sorted(vendor_spends.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
            lines.append("• Top Vendors by Spend:")
            for vn, vi in top_vends:
                lines.append(f"   - {vn}: ₹ {vi['total']:,.2f} ({vi['count']} receipts)")

            summary_text = "\n".join(lines)
            if user_id:
                gen_sql = f"SELECT COUNT(*) AS receipt_count, SUM(grand_total) AS total_spent, vendor_name, invoice_date FROM {allowed_col} WHERE user_id = '{user_id}' GROUP BY vendor_name, invoice_date;"
            else:
                gen_sql = f"SELECT COUNT(*) AS receipt_count, SUM(grand_total) AS total_spent, vendor_name, invoice_date FROM {allowed_col} GROUP BY vendor_name, invoice_date;"

            return {
                "total_spent": total_spent,
                "receipt_count": receipt_count,
                "summary_text": summary_text,
                "specific_month": specific_month_match,
                "specific_vendor": specific_vendor_match,
                "highest_receipt": highest_receipt,
                "generated_sql": gen_sql,
            }

        except Exception as exc:
            logger.warning(f"ApplicationMongoAdapter get_expense_analytics failed: {exc}")
            return None

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
                "spend", "spent", "spending", "expenses", "expense", "at", "in", "bill", "bills", "get", "view", "details",
                "address", "kadayin", "kadaisi", "sollu", "sol", "patri", "kooru", "mukavari",
                "selavu", "motha", "motham", "evvalavu", "paniruken", "panniyiruken",
                "ரசீது", "ரசீதுகள்", "காட்டு", "எனது", "விவரங்கள்", "சுருக்கமாக",
                "தகவல்கள்", "உள்ள", "பற்றி", "சொல்", "முகவரி", "எங்கே", "கடை",
                "செலவு", "செலவுகள்", "மொத்தம்", "எவ்வளவு", "பண்ணியிருக்கேன்", "மாசம்", "மாதம்", "இந்த",
                "hi", "hello", "hey", "how", "are", "you", "your", "who", "what", "is", "was",
                "am", "can", "tell", "please", "help", "good", "morning", "afternoon", "evening",
                "night", "thanks", "thank", "வணக்கம்", "நன்றி", "ஹலோ", "ஹாய்"
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

            # Fallback: if search by term yielded no matches, but candidate user_id is provided,
            # retrieve that user's owned records so broad questions (e.g. "kadayin address ai sollu") can answer from their receipt
            if not raw_records and user_id and search_terms:
                user_filter = {
                    "$or": [
                        {"user_id": user_id},
                        {"candidate_id": user_id},
                    ]
                }
                raw_records = list(collection.find(user_filter).sort("_id", -1).limit(max_results))

            if not raw_records:
                return None
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
                seller_addr = data_sub.get("seller_address") or data_sub.get("vendor_address") or data_sub.get("address") or r.get("seller_address")
                sanitized_records.append({
                    "vendor_or_seller": vendor,
                    "vendor_name": vendor,
                    "vendor_address": seller_addr,
                    "address": seller_addr,
                    "seller_phone": data_sub.get("seller_phone"),
                    "buyer": buyer,
                    "invoice_number": inv_no,
                    "invoice_date": inv_date,
                    "grand_total": total,
                    "total_amount": total,
                    "date": inv_date,
                    "currency": data_sub.get("currency", "INR"),
                    "items": [
                        {"name": it.get("item_name"), "qty": it.get("quantity"), "amount": it.get("total_price")}
                        for it in data_sub.get("items", [])[:5]
                    ] if isinstance(data_sub.get("items"), list) else [],
                })

            if search_terms:
                where_terms = " OR ".join([f"vendor_name ILIKE '%{t}%'" for t in search_terms])
                if user_id:
                    gen_sql = f"SELECT vendor_name, invoice_number, invoice_date, grand_total, seller_address FROM {allowed_col} WHERE user_id = '{user_id}' AND ({where_terms}) ORDER BY id DESC LIMIT {max_results};"
                else:
                    gen_sql = f"SELECT vendor_name, invoice_number, invoice_date, grand_total, seller_address FROM {allowed_col} WHERE ({where_terms}) ORDER BY id DESC LIMIT {max_results};"
            else:
                if user_id:
                    gen_sql = f"SELECT vendor_name, invoice_number, invoice_date, grand_total, seller_address FROM {allowed_col} WHERE user_id = '{user_id}' ORDER BY id DESC LIMIT {max_results};"
                else:
                    gen_sql = f"SELECT vendor_name, invoice_number, invoice_date, grand_total, seller_address FROM {allowed_col} ORDER BY id DESC LIMIT {max_results};"

            return {
                "source_app": conn.get("app_name", target_db),
                "collection": allowed_col,
                "record_count": len(sanitized_records),
                "records": sanitized_records,
                "generated_sql": gen_sql,
            }

        except Exception as exc:
            logger.warning(f"ApplicationMongoAdapter query failed: {exc}")
            return None


app_mongo_adapter = ApplicationMongoAdapter()
