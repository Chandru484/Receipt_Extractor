from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_now_str() -> str:
    """Format current IST time as DD-MM-YYYY HH:MM:SS."""
    return datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")


def get_ist_date_str() -> str:
    """Format current IST date as DD-MM-YYYY."""
    return datetime.now(IST).strftime("%d-%m-%Y")


class WidgetConfig(BaseModel):
    """Customization settings for the frontend embeddable widget."""
    bot_name: str = "Assistant"
    primary_color: str = "#2563eb"
    welcome_message_en: str = "Hello! How can I help you today?"
    welcome_message_ta: str = "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?"
    default_language: str = "en"
    available_languages: List[str] = ["en", "ta"]
    allow_file_uploads: bool = True
    allow_voice_input: bool = True
    allow_speech_output: bool = True
    enable_tawk_to: bool = False
    tawk_to_property_id: Optional[str] = None
    tawk_to_widget_id: Optional[str] = None


class TenantCreate(BaseModel):
    name: str = Field(..., description="Organization or business name")
    admin_email: str = Field(..., description="Primary administrator email")
    admin_password: str = Field(..., min_length=8, description="Initial password")


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    admin_email: str
    created_at: str
    status: str = "active"


class WebsiteCreate(BaseModel):
    tenant_id: str
    name: str = Field(..., description="Website or application label")
    allowed_domains: List[str] = Field(default_factory=list, description="Origins permitted to embed widget")
    widget_config: WidgetConfig = Field(default_factory=WidgetConfig)


class WebsiteResponse(BaseModel):
    website_id: str
    tenant_id: str
    name: str
    allowed_domains: List[str]
    widget_config: WidgetConfig
    created_at: str
    status: str = "active"
