from typing import List
from fastapi import APIRouter, HTTPException, status
from universal_chatbot.backend.app.schemas.tenant_schema import (
    TenantCreate,
    TenantResponse,
    WebsiteCreate,
    WebsiteResponse,
)
from universal_chatbot.backend.app.services.tenant_service import (
    create_tenant,
    get_tenant_by_id,
    register_website,
    get_website_by_id,
    list_websites_for_tenant,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED, summary="Create new tenant")
def create_new_tenant(data: TenantCreate):
    """Register a new organization / tenant."""
    return create_tenant(data)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse, summary="Get tenant by ID")
def get_tenant(tenant_id: str):
    """Retrieve tenant metadata."""
    t = get_tenant_by_id(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


@router.post("/websites", response_model=WebsiteResponse, status_code=status.HTTP_201_CREATED, summary="Register new website/app")
def register_new_website(data: WebsiteCreate):
    """Register a new website or integrated application under a tenant."""
    return register_website(data)


@router.get("/websites/{website_id}", response_model=WebsiteResponse, summary="Get website configuration")
def get_website(website_id: str):
    """Retrieve website configuration and widget styling."""
    site = get_website_by_id(website_id)
    if not site:
        raise HTTPException(status_code=404, detail="Website not found")
    return site


@router.get("/tenants/{tenant_id}/websites", response_model=List[WebsiteResponse], summary="List websites for tenant")
def list_tenant_websites(tenant_id: str):
    """List all websites or applications registered under a tenant."""
    return list_websites_for_tenant(tenant_id)


@router.get("/websites/{website_id}/embed-code", summary="Generate widget integration snippet")
def get_embed_code(website_id: str, host: str = "http://localhost:8080"):
    """Generate the JavaScript snippet to embed into any HTML page or React/Vue app."""
    snippet = f"""<!-- Universal AI Chatbot Widget -->
<script
  src="{host}/widget.js"
  data-website-id="{website_id}"
  async>
</script>"""
    return {
        "website_id": website_id,
        "embed_snippet": snippet,
        "script_url": f"{host}/widget.js",
    }
