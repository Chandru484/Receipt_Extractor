import uuid
import logging
from typing import List, Optional, Dict, Any

from universal_chatbot.backend.app.database.mongodb import get_chatbot_db
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str
from universal_chatbot.backend.app.schemas.package_schema import (
    PackagedQuestionsCreate,
    PackagedQuestionsResponse,
    CandidateSuggestionsResponse,
    CandidateLoginSessionRequest,
    CandidateLoginSessionResponse,
    ChatbotAdminQuestionsUpdate,
    RoleType,
)

logger = logging.getLogger(__name__)

# Default standard packages in both Tamil and English (Bilingual)
DEFAULT_ROLE_PACKAGES: Dict[str, Dict[str, Any]] = {
    "admin": {
        "package_name": "நிர்வாக & நிதி அறிக்கை / Executive & Financial Overview",
        "questions": [
            "இந்த மாத மொத்த வருவாய் என்ன? / What is the total revenue generated this month?",
            "சமீபத்திய இன்வாய்ஸ்கள் மற்றும் நிலுவைத் தொகை / Show recent invoices and pending payments",
            "அதிக செலவு செய்த விற்பனையாளர்கள் யார்? / Which vendors have the highest spend this quarter?",
            "அனைத்து ரசீதுகளையும் பட்டியலிடு / List all receipts across projects",
            "செலுத்தப்பட்ட மொத்த ஜிஎஸ்டி (GST) வரி எவ்வளவு? / What is the total GST tax paid?",
            "கூடுதல் பணி செய்த தொழிலாளர்கள் பட்டியல் / List workers with overtime or shifts",
            "நடப்பு மற்றும் முந்தைய மாத செலவு ஒப்பீடு / Compare monthly expenses vs last month",
            "அதிகம் வாங்கிய டாப் 5 தயாரிப்பு வகைகள் / Top 5 product categories by purchase volume",
            "புதிய விற்பனையாளர் வங்கி கணக்கு விவரங்கள் / New vendor bank account details",
            "நிறுவனத்தின் நிதி நிலை குறித்த சுருக்கம் / Executive business health summary",
        ]
    },
    "worker": {
        "package_name": "தினசரி பணிகள் & மேலாண்மை / Daily Operations & Tasks",
        "questions": [
            "இன்றைய எனது பணிகள் மற்றும் டிஸ்பாட்ச் என்ன? / What are my assigned tasks today?",
            "சரிபார்க்கப்பட வேண்டிய நிலுவை ரசீதுகள் / Show pending receipts waiting for verification",
            "குறைந்த கையிருப்பு உள்ள பொருட்கள் விவரம் / Check low-stock inventory items",
            "இந்த வாரத்திற்கான எனது ஷிப்ட் நேரம் / What is my shift schedule for this week?",
            "ஆவண செயலாக்கத்தில் ஏற்பட்ட பிழைகள் / Show recent document processing errors",
            "கூடுதல் பணி அல்லது விடுப்பு விண்ணப்பம் / How do I submit overtime or leave request?",
            "கிடங்கு பாதுகாப்பு மற்றும் வழிகாட்டுதல்கள் / Safety guidelines for warehouse handling",
            "இன்றைய ஷிப்ட் மேற்பார்வையாளர் யார்? / Who is the supervisor on duty today?",
            "நேற்று செயலாக்கப்பட்ட மொத்த இன்வாய்ஸ்கள் / Total invoices processed yesterday",
            "ஸ்கேனர் அல்லது கருவி குறைபாட்டைப் புகாரளிப்பது எப்படி? / How to report equipment or scanner issue?",
        ]
    },
    "user": {
        "package_name": "வாடிக்கையாளர் சேவை & பில்லிங் / Customer Self-Service & Billing",
        "questions": [
            "எனது சமீபத்திய ஆர்டர் அல்லது இன்வாய்ஸ் நிலை என்ன? / What is the status of my latest invoice?",
            "எனது ரசீதுகளைக் காட்டு / Show my receipts",
            "ரசீது நகலை PDF ஆக பதிவிறக்குவது எப்படி? / How can I download a PDF copy of my recent receipt?",
            "எனது பில்லில் உள்ள வரிகள் மற்றும் ஜிஎஸ்டி விளக்கம் / Explain tax breakdown on my bill",
            "ஆதரவு பெற்ற கட்டண மற்றும் வங்கி முறைகள் / What payment methods are supported?",
            "பில்லிங் முகவரி அல்லது ஜிஎஸ்டி எண்ணை மாற்றுவது எப்படி? / How do I update billing address or GSTIN?",
            "கடந்த 30 நாட்களின் எனது கொள்முதல் வரலாறு / Show my purchase history for last 30 days",
            "பணம் திரும்பப்பெறுதல் மற்றும் ரத்து செய்யும் கொள்கை / What is refund and cancellation policy?",
            "வாடிக்கையாளர் சேவை முகவரிடம் பேச வேண்டும் / Talk to a human support agent",
            "பில்லில் உள்ள தவறான கட்டணத்தைப் புகாரளிப்பது எப்படி? / How to report a billing discrepancy?",
        ]
    }
}


class PackageService:
    """
    Manages role-specific question packages, candidate profile isolation,
    and Chatbot Admin project management across physically separated MongoDB collections.
    """

    def _sanitize(self, val: str) -> str:
        return val.replace(" ", "_").lower().strip()

    def _get_questions_col(self, project_id: str, role: str):
        db = get_chatbot_db()
        if db is None:
            return None
        return db[f"{self._sanitize(project_id)}_{self._sanitize(role)}_questions"]

    def _get_candidates_col(self, project_id: str, role: str):
        db = get_chatbot_db()
        if db is None:
            return None
        # Candidate collections: e.g. proj_erp_admins, proj_erp_workers, proj_erp_users
        return db[f"{self._sanitize(project_id)}_{self._sanitize(role)}s"]

    def process_login_session(self, req: CandidateLoginSessionRequest) -> CandidateLoginSessionResponse:
        """
        Invoked when coworker's backend transmits candidate login with dynamic package questions.
        1. Resolves candidate ID (admin_id, worker_id, or user_id).
        2. Upserts candidate profile in the role's separate MongoDB collection.
        3. Saves/updates the 10 package questions into {project_id}_{role}_questions.
        4. Returns active suggested questions ready for the widget.
        """
        # Resolve candidate ID
        cand_id = req.admin_id or req.worker_id or req.user_id or req.candidate_id or f"{req.role}_{uuid.uuid4().hex[:8]}"
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now_str = get_ist_now_str()
        db = get_chatbot_db()

        # 1. Upsert candidate profile in separate collection (e.g. proj_demo_admins, proj_demo_workers, etc.)
        cand_col = self._get_candidates_col(req.project_id, req.role)
        if cand_col is not None:
            profile_doc = {
                "candidate_id": cand_id,
                "project_id": req.project_id,
                "role": req.role,
                "name": req.candidate_name or f"{req.role.capitalize()} {cand_id}",
                "email": req.candidate_email,
                "metadata": req.metadata,
                "last_login": now_str,
            }
            cand_col.update_one(
                {"candidate_id": cand_id, "project_id": req.project_id},
                {"$set": profile_doc, "$setOnInsert": {"created_at": now_str}},
                upsert=True
            )

        # 2. If package questions are sent, save/update them in {project_id}_{role}_questions
        questions_saved_count = 0
        if req.package_questions and len(req.package_questions) > 0:
            cleaned_questions = [q.strip() for q in req.package_questions if q and q.strip()]
            if cleaned_questions:
                self.save_package(PackagedQuestionsCreate(
                    project_id=req.project_id,
                    role=req.role,
                    package_name=req.package_name or f"{req.role.capitalize()} Custom Package",
                    questions=cleaned_questions,
                    target_user_id=cand_id,
                    metadata=req.metadata,
                ))
                questions_saved_count = len(cleaned_questions)

        # 3. Fetch active questions for response
        sugg = self.get_candidate_suggestions(req.project_id, req.role, candidate_id=cand_id)

        return CandidateLoginSessionResponse(
            status="success",
            project_id=req.project_id,
            role=req.role,
            candidate_id=cand_id,
            session_id=session_id,
            questions_saved=questions_saved_count,
            suggested_questions=sugg.suggested_questions,
            message=f"Session initialized for {req.role} '{cand_id}'. {len(sugg.suggested_questions)} questions active.",
        )

    def save_package(self, data: PackagedQuestionsCreate) -> PackagedQuestionsResponse:
        """Save package of questions into the role's dedicated collection for this project."""
        col = self._get_questions_col(data.project_id, data.role)
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

    def admin_modify_questions(self, project_id: str, update: ChatbotAdminQuestionsUpdate) -> Dict[str, Any]:
        """
        Direct method for Chatbot Admins to view and modify/edit questions for any project and role.
        """
        res = self.save_package(PackagedQuestionsCreate(
            project_id=project_id,
            role=update.role,
            package_name=update.package_name or f"Admin Modified {update.role.capitalize()} Package",
            questions=update.questions,
            target_user_id=update.target_user_id,
        ))
        return {
            "status": "updated",
            "project_id": project_id,
            "role": update.role,
            "package_id": res.package_id,
            "questions_count": len(res.questions),
            "questions": res.questions,
            "updated_at": res.created_at,
        }

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
        col = self._get_questions_col(project_id, role)
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

    def get_project_all_packages(self, project_id: str) -> Dict[str, Any]:
        """Allows Chatbot Admin to view all questions across all 3 roles for a project."""
        results = {}
        for r in ["admin", "worker", "user"]:
            sugg = self.get_candidate_suggestions(project_id, role=r)
            results[r] = {
                "package_name": sugg.package_name,
                "questions": sugg.suggested_questions,
            }
        return {"project_id": project_id, "packages": results}

    def get_project_data_overview(self, project_id: str) -> Dict[str, Any]:
        """Allows Chatbot Admin to inspect any project's candidates, questions, and chats."""
        db = get_chatbot_db()
        if db is None:
            return {"error": "Database unavailable"}

        safe_p = self._sanitize(project_id)
        admin_col = db[f"{safe_p}_admins"]
        worker_col = db[f"{safe_p}_workers"]
        user_col = db[f"{safe_p}_users"]
        conv_col = db["conversations"]

        return {
            "project_id": project_id,
            "counts": {
                "admins": admin_col.count_documents({}),
                "workers": worker_col.count_documents({}),
                "users": user_col.count_documents({}),
                "conversations": conv_col.count_documents({"website_id": project_id}),
            },
            "recent_admins": list(admin_col.find({}, {"_id": 0}).limit(5)),
            "recent_workers": list(worker_col.find({}, {"_id": 0}).limit(5)),
            "recent_users": list(user_col.find({}, {"_id": 0}).limit(5)),
        }

    def list_all_active_projects(self) -> List[Dict[str, Any]]:
        """List all projects registered in the chatbot platform for Chatbot Admins."""
        db = get_chatbot_db()
        if db is None:
            return []

        # Find unique projects across websites collection or dynamic collection names
        sites_col = db["websites"]
        projects = []
        if sites_col is not None:
            sites = list(sites_col.find({}, {"_id": 0, "website_id": 1, "name": 1, "created_at": 1}))
            for s in sites:
                projects.append({
                    "project_id": s.get("website_id"),
                    "name": s.get("name", s.get("website_id")),
                    "created_at": s.get("created_at"),
                })

        # Check if project list is empty, return default
        if not projects:
            projects.append({"project_id": "site_demo", "name": "Default Project", "created_at": "Active"})

        return projects


package_service = PackageService()
