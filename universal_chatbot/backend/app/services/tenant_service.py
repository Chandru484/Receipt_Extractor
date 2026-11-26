import re
import logging
import uuid
from typing import Any, Dict, List, Optional
from universal_chatbot.backend.app.database import collections
from universal_chatbot.backend.app.schemas.tenant_schema import (
    TenantCreate,
    TenantResponse,
    WebsiteCreate,
    WebsiteResponse,
    WidgetConfig,
    get_ist_now_str,
)

logger = logging.getLogger(__name__)


def create_tenant(data: TenantCreate) -> TenantResponse:
    """Create a new tenant in the platform."""
    tenants = collections.get_tenants_collection()
    tenant_id = f"ten_{uuid.uuid4().hex[:12]}"
    now_str = get_ist_now_str()

    doc = {
        "tenant_id": tenant_id,
        "name": data.name,
        "admin_email": data.admin_email.lower().strip(),
        "created_at": now_str,
        "status": "active",
    }
    if tenants is not None:
        tenants.insert_one(doc)

    return TenantResponse(
        tenant_id=tenant_id,
        name=data.name,
        admin_email=data.admin_email,
        created_at=now_str,
        status="active",
    )


def get_tenant_by_id(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve tenant document by ID."""
    tenants = collections.get_tenants_collection()
    if tenants is None:
        return None
    return tenants.find_one({"tenant_id": tenant_id}, {"_id": 0})


def register_website(data: WebsiteCreate) -> WebsiteResponse:
    """Register a new website or integrated application under a tenant."""
    websites = collections.get_websites_collection()
    website_id = f"site_{uuid.uuid4().hex[:12]}"
    now_str = get_ist_now_str()

    doc = {
        "website_id": website_id,
        "tenant_id": data.tenant_id,
        "name": data.name,
        "allowed_domains": data.allowed_domains,
        "widget_config": data.widget_config.model_dump(),
        "created_at": now_str,
        "status": "active",
    }
    if websites is not None:
        websites.insert_one(doc)

    return WebsiteResponse(
        website_id=website_id,
        tenant_id=data.tenant_id,
        name=data.name,
        allowed_domains=data.allowed_domains,
        widget_config=data.widget_config,
        created_at=now_str,
        status="active",
    )


def get_website_by_id(website_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve website configuration by ID or auto-provision a new project record in MongoDB."""
    websites = collections.get_websites_collection()
    if websites is not None:
        existing = websites.find_one({"website_id": website_id}, {"_id": 0})
        if existing:
            return existing

    # Auto-provision new project website document in MongoDB
    clean_id = re.sub(r"[^\w\-]", "_", str(website_id).strip())
    now_str = get_ist_now_str()
    new_doc = {
        "website_id": website_id,
        "tenant_id": "ten_default",
        "name": f"{clean_id.replace('_', ' ').title()} Project",
        "allowed_domains": ["*"],
        "widget_config": {
            "bot_name": "Assistant",
            "primary_color": "#2563eb",
            "welcome_message_en": "Hello! How can I help you today?",
            "welcome_message_ta": "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?",
            "default_language": "en",
            "available_languages": ["en", "ta"],
            "allow_file_uploads": True,
            "allow_voice_input": True,
            "allow_speech_output": True,
            "enable_tawk_to": False,
        },
        "created_at": now_str,
        "status": "active",
    }
    if websites is not None:
        try:
            websites.insert_one(dict(new_doc))
            new_doc.pop("_id", None)
        except Exception as e:
            logger.warning(f"Could not auto-insert website document: {e}")
    return new_doc


def list_websites_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """List all websites registered under a tenant."""
    websites = collections.get_websites_collection()
    if websites is None:
        return []
    return list(websites.find({"tenant_id": tenant_id}, {"_id": 0}))
