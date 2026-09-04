from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import uuid
from ..database import get_db
from .. import models, schemas
from .. import auth
from ..dependencies import get_current_user, require_csrf
from ..utils.security import generate_reset_token
from .entries import serialize_entry
from ..services.users import authenticate_user, create_user, find_existing_user
from ..config import settings
from ..rate_limit import rate_limit

router = APIRouter(prefix="/users", tags=["users"])


def _store_refresh_session(db: Session, user: models.User, token: str, family_id: str | None = None) -> models.RefreshSession:
    payload = auth.verify_token(token, is_refresh=True)
    session = models.RefreshSession(
        jti_hash=auth.hash_token_jti(payload["jti"]), user_id=user.id,
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
    db.add(session)
    return session

@router.post("/register", response_model=schemas.UserResponse, dependencies=[Depends(rate_limit("rate_limit_register", "api-register"))])
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = find_existing_user(db, user.username, user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )
    
    # Create new user
    return create_user(db, user.username, user.email, user.password)

@router.post("/login", response_model=schemas.Token, dependencies=[Depends(rate_limit("rate_limit_login", "api-login"))])
def login_user(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = authenticate_user(db, user.username, user.password)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    claims = {"sub": db_user.username, "ver": db_user.token_version}
    access_token = auth.create_access_token(data=claims)
    refresh_token = auth.create_refresh_token(data=claims)
    _store_refresh_session(db, db_user, refresh_token)
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/refresh", response_model=schemas.Token, dependencies=[Depends(rate_limit("rate_limit_refresh", "api-refresh"))])
def refresh_token(token_data: schemas.TokenRefresh, db: Session = Depends(get_db)):
    payload = auth.verify_token(token_data.refresh_token, is_refresh=True)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    db_user = db.query(models.User).filter(models.User.username == username).first()
    jti_hash = auth.hash_token_jti(payload.get("jti", ""))
    session = db.query(models.RefreshSession).filter(models.RefreshSession.jti_hash == jti_hash).with_for_update().first()
    if session and session.revoked_at:
        now = datetime.now(timezone.utc)
        db.query(models.RefreshSession).filter(
            models.RefreshSession.family_id == session.family_id,
            models.RefreshSession.revoked_at.is_(None),
        ).update({"revoked_at": now})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if not db_user or not db_user.is_active or payload.get("ver", 0) != db_user.token_version or not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    claims = {"sub": username, "ver": db_user.token_version}
    access_token = auth.create_access_token(data=claims)
    refresh_token = auth.create_refresh_token(data=claims)
    replacement = _store_refresh_session(db, db_user, refresh_token, session.family_id)
    session.revoked_at = datetime.now(timezone.utc)
    session.replaced_by_hash = replacement.jti_hash
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/password-reset-request", dependencies=[Depends(rate_limit("rate_limit_password_reset_request", "reset-request"))])
def password_reset_request(
    request: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    if settings.environment.lower() == "production" or not settings.password_reset_enabled:
        return {"message": "If the email exists, a reset link has been sent"}
    user = db.query(models.User).filter(models.User.email == request.email).first()
    development_token = None
    if user:
        reset_token = generate_reset_token()
        development_token = reset_token
        now = datetime.now(timezone.utc)
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used_at.is_(None),
        ).update({"used_at": now})
        db_token = models.PasswordResetToken(
            token_hash=auth.hash_opaque_token(reset_token),
            user_id=user.id,
            expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
        )
        db.add(db_token)
        db.commit()
        
    
    # Always return success to prevent email enumeration
    response = {"message": "If the email exists, a reset link has been sent"}
    if development_token:
        response["development_reset_token"] = development_token
    return response

@router.post("/password-reset", dependencies=[Depends(rate_limit("rate_limit_password_reset_submit", "reset-submit"))])
def password_reset(reset_data: schemas.PasswordReset, db: Session = Depends(get_db)):
    if settings.environment.lower() == "production" or not settings.password_reset_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Password reset is unavailable")
    token_hash = auth.hash_opaque_token(reset_data.token)
    reset_token = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token_hash == token_hash,
        models.PasswordResetToken.used_at.is_(None),
        models.PasswordResetToken.expires_at > datetime.now(timezone.utc)
    ).with_for_update().first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update user password
    reset_token.user.hashed_password = auth.get_password_hash(reset_data.new_password)
    reset_token.user.token_version += 1
    db.query(models.RefreshSession).filter(models.RefreshSession.user_id == reset_token.user_id, models.RefreshSession.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
    used_at = datetime.now(timezone.utc)
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == reset_token.user_id,
        models.PasswordResetToken.used_at.is_(None),
    ).update({"used_at": used_at})
    db.commit()
    
    return {"message": "Password reset successfully"}

@router.get("/me", response_model=schemas.UserWithEntries)
def get_current_user_info(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "created_at": current_user.created_at,
        "entries": [serialize_entry(entry) for entry in current_user.entries],
    }

@router.post("/logout")
def logout(_csrf: None = Depends(require_csrf), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.token_version += 1
    db.query(models.RefreshSession).filter(models.RefreshSession.user_id == current_user.id, models.RefreshSession.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    return {"message": "Logged out successfully"}

@router.get("/export")
def export_account_data(current_user: models.User = Depends(get_current_user)):
    return {
        "user": {
            "username": current_user.username,
            "email": current_user.email,
            "created_at": current_user.created_at,
        },
        "entries": [serialize_entry(entry) for entry in current_user.entries],
    }

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    confirmation: schemas.AccountDelete,
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not auth.verify_password(confirmation.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect")
    db.delete(current_user)
    db.commit()
    return None
