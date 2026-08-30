from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from .database import engine
from . import models

# Import routers
from .routes import users, entries

app = FastAPI(
    title="MindMate",
    description="AI-Powered Mental Wellness Journal with Advanced Emotion Analysis",
    version="5.0.0",
    docs_url="/docs",  # Keep original docs URL for now
    redoc_url="/redoc"
)

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers (Week 1-4 features)
app.include_router(users.router, prefix="/api")
app.include_router(entries.router, prefix="/api")

# Frontend routes (Week 5) - import only if exists
try:
    from .routes import frontend
    app.include_router(frontend.router)
    print("✅ Frontend routes loaded")
except ImportError:
    print("⚠️ Frontend routes not available yet")

# Serve static files if frontend exists
try:
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "frontend", "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        print("✅ Static files mounted")
except:
    print("⚠️ Static files not available yet")

@app.get("/")
async def root():
    return {
        "message": "Welcome to MindMate API",
        "version": "5.0.0",
        "status": "running",
        "endpoints": {
            "api_docs": "/docs",
            "api_redoc": "/redoc",
            "user_auth": "/api/users/*",
            "journal_entries": "/api/entries/*",
            "frontend": "Coming soon - check /dashboard after setup"
        }
    }

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
                "emotion_trends": "GET /api/entries/emotion-trends"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)