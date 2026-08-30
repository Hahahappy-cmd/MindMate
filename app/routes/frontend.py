from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from ..database import get_db
from ..dependencies import get_current_user_optional
from .. import models
from ..auth import get_password_hash, verify_password, create_access_token

router = APIRouter(tags=["frontend"])

# Set up templates directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Home page accessed - User: {current_user}")
    print(f"🔍 Request headers: {dict(request.headers)}")
    
    if current_user:
        print("✅ User authenticated, redirecting to dashboard")
        return RedirectResponse(url="/dashboard")
    
    print("ℹ️ No authenticated user, showing home page")
    return templates.TemplateResponse("index.html", {"request": request, "current_user": current_user})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Login page accessed - User: {current_user}")
    
    # Check for success message from registration
    registered = request.query_params.get("registered")
    success_message = None
    if registered == "true":
        success_message = "Registration successful! Please login."
    
    if current_user:
        print("✅ User already authenticated, redirecting to dashboard")
        return RedirectResponse(url="/dashboard")
    
    print("ℹ️ Showing login page")
    return templates.TemplateResponse(
        "login.html", 
        {
            "request": request, 
            "current_user": current_user,
            "success": success_message
        }
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Register page accessed - User: {current_user}")
    
    if current_user:
        print("✅ User already authenticated, redirecting to dashboard")
        return RedirectResponse(url="/dashboard")
    
    print("ℹ️ Showing register page")
    return templates.TemplateResponse("register.html", {"request": request, "current_user": current_user})

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Dashboard page accessed - User: {current_user}")
    
    if not current_user:
        print("❌ No authenticated user, redirecting to login")
        return RedirectResponse(url="/login")
    
    print("✅ Showing dashboard")
    return templates.TemplateResponse("dashboard.html", {"request": request, "current_user": current_user})

@router.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Journal page accessed - User: {current_user}")
    
    if not current_user:
        print("❌ No authenticated user, redirecting to login")
        return RedirectResponse(url="/login")
    
    print("✅ Showing journal page")
    return templates.TemplateResponse("journal.html", {"request": request, "current_user": current_user})

@router.get("/weekly-summary", response_class=HTMLResponse)
async def weekly_summary_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Weekly summary page accessed - User: {current_user}")
    
    if not current_user:
        print("❌ No authenticated user, redirecting to login")
        return RedirectResponse(url="/login")
    
    print("✅ Showing weekly summary page")
    return templates.TemplateResponse("summary.html", {"request": request, "current_user": current_user})

# Test route without authentication
@router.get("/test-no-auth", response_class=HTMLResponse)
async def test_no_auth(request: Request):
    print("🔵 TEST ROUTE HIT - No auth!")
    return HTMLResponse(content="<h1>Test Success!</h1><p>If you see this, routing works.</p>")

@router.post("/register")
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
    print(f"📝 Registration attempt for: {username}")
    
    # Validate passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request, 
                "error": "Passwords do not match",
                "current_user": None
            }
        )
    
    # Validate password length
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request, 
                "error": "Password must be at least 8 characters long",
                "current_user": None
            }
        )
    
    # Check if user exists
    existing_user = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()
    
    if existing_user:
        if existing_user.username == username:
            return templates.TemplateResponse(
                "register.html", 
                {
                    "request": request, 
                    "error": "Username already taken",
                    "current_user": None
                }
            )
        else:
            return templates.TemplateResponse(
                "register.html", 
                {
                    "request": request, 
                    "error": "Email already registered",
                    "current_user": None
                }
            )
    
    # Create new user
    hashed_password = get_password_hash(password)
    new_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    print(f"✅ User created: {username}")
    
    # Redirect to login with success message
    response = RedirectResponse(url="/login?registered=true", status_code=303)
    return response

@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handle login form submission
    """
    print(f"🔑 Login attempt for: {username}")
    
    # Find user by username or email
    user = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == username)
    ).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html", 
            {
                "request": request, 
                "error": "Invalid username or password",
                "current_user": None
            }
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    
    print(f"✅ Login successful for: {username}")
    
    # Redirect to dashboard with token in cookie
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,  # Prevents JavaScript access
        max_age=1800,  # 30 minutes
        expires=1800,
        path="/",
        secure=False,
        samesite="lax"
    )
    
    return response

@router.get("/logout")
async def logout():
    """
    Handle logout
    """
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response

# Optional: Add a profile page
@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Profile page accessed - User: {current_user}")
    
    if not current_user:
        print("❌ No authenticated user, redirecting to login")
        return RedirectResponse(url="/login")
    
    print("✅ Showing profile page")
    return templates.TemplateResponse("profile.html", {"request": request, "current_user": current_user})

# Optional: Add settings page
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, current_user: models.User = Depends(get_current_user_optional)):
    print(f"🔍 Settings page accessed - User: {current_user}")
    
    if not current_user:
        print("❌ No authenticated user, redirecting to login")
        return RedirectResponse(url="/login")
    
    print("✅ Showing settings page")
    return templates.TemplateResponse("settings.html", {"request": request, "current_user": current_user})