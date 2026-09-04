from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import secrets
from datetime import datetime, timezone
from ..database import get_db
from ..dependencies import get_current_user_optional
from .. import models
from ..auth import create_access_token
from ..config import settings
from ..services.users import authenticate_user, create_user, find_existing_user
from ..rate_limit import rate_limit

router = APIRouter(tags=["frontend"])

# Set up templates directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "index.html", {"current_user": current_user})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    # Check for success message from registration
    registered = request.query_params.get("registered")
    success_message = None
    if registered == "true":
        success_message = "Registration successful! Please login."
    
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request,
        "login.html", 
        {
            "current_user": current_user,
            "success": success_message
        }
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "register.html", {"current_user": current_user})

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "dashboard.html", {"current_user": current_user})

@router.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "journal.html", {"current_user": current_user})

@router.get("/journal/{entry_id}", response_class=HTMLResponse)
async def journal_detail(
    entry_id: int,
    request: Request,
    current_user: models.User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    entry = db.query(models.JournalEntry).filter(
        models.JournalEntry.id == entry_id,
        models.JournalEntry.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return templates.TemplateResponse(
        request,
        "entry_detail.html",
        {"current_user": current_user, "entry": entry},
    )

@router.get("/weekly-summary", response_class=HTMLResponse)
async def weekly_summary_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "summary.html", {"current_user": current_user})

@router.post("/register", dependencies=[Depends(rate_limit("rate_limit_register", "form-register"))])
async def register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handle registration form submission
    """
    # Validate passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            request,
            "register.html", 
            {
                "error": "Passwords do not match",
                "current_user": None
            }
        )

    if len(username) < 3 or len(username) > 50 or not all(char.isalnum() or char in "_-" for char in username):
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Username must be 3–50 characters using letters, numbers, _ or -", "current_user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    # Validate password length
    if len(password) < 8 or len(password) > 128:
        return templates.TemplateResponse(
            request,
            "register.html", 
            {
                "error": "Password must be at least 8 characters long",
                "current_user": None
            }
        )
    
    # Check if user exists
    existing_user = find_existing_user(db, username, email)
    
    if existing_user:
        if existing_user.username == username:
            return templates.TemplateResponse(
                request,
                "register.html", 
                {
                    "error": "Username already taken",
                    "current_user": None
                }
            )
        else:
            return templates.TemplateResponse(
                request,
                "register.html", 
                {
                    "error": "Email already registered",
                    "current_user": None
                }
            )
    
    # Create new user
    create_user(db, username, email, password)
    
    # Redirect to login with success message
    response = RedirectResponse(url="/login?registered=true", status_code=303)
    return response

@router.post("/login", dependencies=[Depends(rate_limit("rate_limit_login", "form-login"))])
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handle login form submission
    """
    # Find user by username or email
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html", 
            {
                "error": "Invalid username or password",
                "current_user": None
            }
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username, "ver": user.token_version})
    
    # Redirect to dashboard with token in cookie
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,  # Prevents JavaScript access
        max_age=settings.access_token_expire_minutes * 60,
        expires=settings.access_token_expire_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
    )
    response.set_cookie(
        key="csrf_token",
        value=secrets.token_urlsafe(32),
        httponly=False,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
    )
    
    return response

@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user_optional)):
    """
    Handle logout
    """
    cookie_token = request.cookies.get("csrf_token")
    if not cookie_token or not secrets.compare_digest(cookie_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    if current_user:
        current_user.token_version += 1
        db.query(models.RefreshSession).filter(models.RefreshSession.user_id == current_user.id, models.RefreshSession.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
        db.commit()
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("csrf_token")
    return response

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "profile.html", {"current_user": current_user})

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "settings.html", {"current_user": current_user})
