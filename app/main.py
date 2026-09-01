from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
import secrets
from .config import settings
from .database import engine
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in settings.allowed_origins.split(",") if value.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[value.strip() for value in settings.trusted_hosts.split(",") if value.strip()])

@app.middleware("http")
async def ensure_csrf_cookie(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
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
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith("/api/") or request.cookies.get("access_token"):
        response.headers["Cache-Control"] = "no-store"
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
