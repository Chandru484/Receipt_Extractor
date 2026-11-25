import uuid
import logging
from typing import List, Optional, Dict, Any

from universal_chatbot.backend.app.database.mongodb import get_chatbot_db
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str
from universal_chatbot.backend.app.schemas.package_schema import (
    PackagedQuestionsCreate,
    PackagedQuestionsResponse,
    CandidateSuggestionsResponse,
    RoleType,
)

logger = logging.getLogger(__name__)

# Default standard packages if the coworker backend has not yet pushed custom ones
DEFAULT_ROLE_PACKAGES: Dict[str, Dict[str, Any]] = {
    "admin": {
        "package_name": "Executive & Financial Overview",
        "questions": [
            "What is the total revenue generated this month?",
            "Show recent high-value invoices and pending payments",
            "Which vendors have the highest spend this quarter?",
            "List workers who had overtime or shift changes",
            "Show active system alerts or pending approvals",
            "What is the total tax (GST) paid across recent invoices?",
            "Compare monthly expenses between this month and last month",
            "Show the top 5 product categories by purchase volume",
            "List newly added vendor accounts and bank details",
            "Give me an executive summary of current business health",
        ]
    },
    "worker": {
        "package_name": "Daily Operations & Tasks",
        "questions": [
            "What are my assigned tasks or dispatches for today?",
            "Show pending receipt scans waiting for verification",
            "What is my shift schedule for this week?",
            "Check current inventory status for low-stock items",
            "How do I submit an overtime or leave request?",
            "Show recent errors flagged during document processing",
            "What are the safety guidelines for warehouse handling?",
            "Who is the supervisor on duty for today's shift?",
            "How many invoices did our team process yesterday?",
            "Where do I report an equipment or scanner issue?",
        ]
    },
    "user": {
        "package_name": "Customer Self-Service & Billing",
        "questions": [
            "What is the status of my latest order or invoice?",
            "How can I download a PDF copy of my recent receipt?",
            "What payment methods and bank transfers are supported?",
            "How do I update my billing address or GSTIN?",
            "Can you explain the tax breakdown on my bill?",
            "What is the refund and cancellation policy?",
            "How can I contact customer support or request a call?",
            "Show my purchase history for the last 30 days",
            "Are there any active discounts or loyalty credits on my account?",
            "How do I report a billing discrepancy or wrong item?",
        ]
    }
}


class PackageService:
    """Manages role-specific question packages stored in physically separated MongoDB collections per project."""

    def _get_collection(self, project_id: str, role: str):
        db = get_chatbot_db()
        if db is None:
            return None
        safe_proj = project_id.replace(" ", "_").lower()
        safe_role = role.lower()
        # Separate physical collection: e.g. proj_demo_admin_questions
        return db[f"{safe_proj}_{safe_role}_questions"]

    def save_package(self, data: PackagedQuestionsCreate) -> PackagedQuestionsResponse:
        """Save package of questions into the role's dedicated collection for this project."""
        col = self._get_collection(data.project_id, data.role)
        package_id = f"pkg_{uuid.uuid4().hex[:10]}"
        now_str = get_ist_now_str()

        doc = {
            "package_id": package_id,
            "project_id": data.project_id,
            "role": data.role,
            "package_name": data.package_name,
            "questions": data.questions,
            "target_user_id": data.target_user_id,
            "metadata": data.metadata,
            "created_at": now_str,
            "is_active": True,
        }

        if col is not None:
            # Deactivate older packages for this target user or role to keep newest active
            filter_old: Dict[str, Any] = {"project_id": data.project_id, "role": data.role}
            if data.target_user_id:
                filter_old["target_user_id"] = data.target_user_id
            else:
                filter_old["target_user_id"] = None
            col.update_many(filter_old, {"$set": {"is_active": False}})

            col.insert_one(doc)

        return PackagedQuestionsResponse(
            package_id=package_id,
            project_id=data.project_id,
            role=data.role,
            package_name=data.package_name,
            questions=data.questions,
            target_user_id=data.target_user_id,
            created_at=now_str,
            is_active=True,
        )

    def get_candidate_suggestions(
        self,
        project_id: str,
        role: RoleType = "user",
        candidate_id: Optional[str] = None
    ) -> CandidateSuggestionsResponse:
        """
        Retrieve the 10 package questions customized for the candidate's verified role and ID.
        Strict RBAC: An admin collection is NEVER queried for workers or users.
        """
        col = self._get_collection(project_id, role)
        questions: List[str] = []
        package_name: Optional[str] = None

        if col is not None:
            # First check for individual-specific package
            if candidate_id:
                specific = col.find_one(
                    {"target_user_id": candidate_id, "is_active": True},
                    sort=[("_id", -1)]
                )
                if specific and specific.get("questions"):
                    questions = specific["questions"]
                    package_name = specific.get("package_name")

            # If no individual package, get the role-wide package
            if not questions:
                general = col.find_one(
                    {"is_active": True, "$or": [{"target_user_id": None}, {"target_user_id": {"$exists": False}}]},
                    sort=[("_id", -1)]
                )
                if general and general.get("questions"):
                    questions = general["questions"]
                    package_name = general.get("package_name")

        # Fallback to rich built-in default package if coworker hasn't uploaded custom ones yet
        if not questions:
            default_pkg = DEFAULT_ROLE_PACKAGES.get(role, DEFAULT_ROLE_PACKAGES["user"])
            questions = default_pkg["questions"]
            package_name = default_pkg["package_name"]

        return CandidateSuggestionsResponse(
            project_id=project_id,
            role=role,
            candidate_id=candidate_id,
            package_name=package_name,
            suggested_questions=questions,
        )


package_service = PackageService()
