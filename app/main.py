from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
import secrets
from .config import settings
from .database import engine, migrate_existing_sqlite_schema
from . import models

# Import routers
from .routes import users, entries

app = FastAPI(
    title="MindMate",
    description="AI-Powered Mental Wellness Journal with Advanced Emotion Analysis",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Create database tables
models.Base.metadata.create_all(bind=engine)
migrate_existing_sqlite_schema()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def ensure_csrf_cookie(request, call_next):
    csrf_token = request.cookies.get("csrf_token")
    should_set_csrf = bool(request.cookies.get("access_token") and not csrf_token)
    if should_set_csrf:
        csrf_token = secrets.token_urlsafe(32)
    request.state.csrf_token = csrf_token or ""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if should_set_csrf:
        response.set_cookie(
            "csrf_token",
            csrf_token,
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
            max_age=settings.access_token_expire_minutes * 60,
        )
    return response

app.include_router(users.router, prefix="/api")
app.include_router(entries.router, prefix="/api")

from .routes import frontend
app.include_router(frontend.router)

import os
static_dir = os.path.join(os.path.dirname(__file__), "frontend", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "5.0.0"
    }

@app.get("/api/")
async def api_root():
    return {
        "message": "MindMate API",
        "version": "5.0.0",
        "endpoints": {
            "auth": {
                "register": "POST /api/users/register",
                "login": "POST /api/users/login",
                "refresh": "POST /api/users/refresh",
                "me": "GET /api/users/me",
                "password_reset": "POST /api/users/password-reset-request"
            },
            "entries": {
                "create": "POST /api/entries/",
                "list": "GET /api/entries/",
                "get": "GET /api/entries/{id}",
                "update": "PUT /api/entries/{id}",
                "delete": "DELETE /api/entries/{id}",
                "weekly_summary": "GET /api/entries/weekly-summary",
                "emotion_trends": "GET /api/entries/emotion-trends",
                "long_term_analytics": "GET /api/entries/long-term-analytics?period=30",
                "analysis_status": "GET /api/entries/{id}/analysis-status"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
