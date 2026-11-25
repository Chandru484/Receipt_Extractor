import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from universal_chatbot.backend.app.core.config import chatbot_settings
from universal_chatbot.backend.app.database.mongodb import check_mongo_health
from universal_chatbot.backend.app.database.indexes import ensure_indexes
from universal_chatbot.backend.app.api.v1.chat_routes import router as chat_router
from universal_chatbot.backend.app.api.v1.admin_routes import router as admin_router
from universal_chatbot.backend.app.api.v1.document_routes import router as document_router
from universal_chatbot.backend.app.api.v1.voice_routes import router as voice_router
from universal_chatbot.backend.app.api.v1.package_routes import router as package_router
from universal_chatbot.backend.app.api.v1.chatbot_admin_routes import router as chatbot_admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Build platform MongoDB indexes on startup
    ensure_indexes()
    yield


app = FastAPI(
    title="Universal AI Chatbot Platform",
    description=(
        "Standalone, reusable, multilingual AI Chatbot platform supporting "
        "website knowledge, user document Q&A, external database retrieval, "
        "Tamil & English languages, voice synthesis, and Tawk.to human handoff."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routers
app.include_router(chat_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(package_router, prefix="/api/v1")
app.include_router(chatbot_admin_router, prefix="/api/v1")


@app.get("/health", summary="Platform Health Check")
def health_check():
    """Diagnostic health check verifying API and MongoDB status."""
    return {
        "status": "healthy",
        "service": "Universal AI Chatbot Platform",
        "version": "1.0.0",
        "mongodb": check_mongo_health(),
        "ai_keys_configured": len(chatbot_settings.get_groq_keys()),
        "fallback_provider": chatbot_settings.CHATBOT_FALLBACK_PROVIDER,
    }


# Widget JS static route
WIDGET_PATH = Path(__file__).resolve().parent.parent.parent / "widget" / "widget.js"


@app.get("/widget.js", include_in_schema=False)
def serve_widget_script():
    """Serve the standalone embeddable JavaScript chatbot widget."""
    if WIDGET_PATH.exists():
        return FileResponse(WIDGET_PATH, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"detail": "Widget script not built yet."})


# Demo page
DEMO_PATH = Path(__file__).resolve().parent.parent.parent / "widget" / "index.html"
CHATBOT_ADMIN_PATH = Path(__file__).resolve().parent.parent.parent.parent / "chatbot_admin.html"


@app.get("/demo", include_in_schema=False)
def serve_demo_page():
    """Serve demo page illustrating widget embedded on an external website."""
    if DEMO_PATH.exists():
        return FileResponse(DEMO_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"detail": "Demo page not found."})


@app.get("/chatbot-admin", include_in_schema=False)
def serve_chatbot_admin():
    """Serve the multi-project Chatbot Admin Dashboard."""
    if CHATBOT_ADMIN_PATH.exists():
        return FileResponse(CHATBOT_ADMIN_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"detail": "chatbot_admin.html not found."})
