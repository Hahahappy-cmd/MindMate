from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import get_db
from .. import models, schemas
from .. import auth
from ..dependencies import get_current_user, require_csrf
from ..utils.security import generate_reset_token
from .entries import serialize_entry
from ..services.users import authenticate_user, create_user, find_existing_user

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register", response_model=schemas.UserResponse)
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

@router.post("/login", response_model=schemas.Token)
def login_user(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = authenticate_user(db, user.username, user.password)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    access_token = auth.create_access_token(data={"sub": db_user.username})
    refresh_token = auth.create_refresh_token(data={"sub": db_user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/refresh", response_model=schemas.Token)
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
    if not db_user or not db_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    access_token = auth.create_access_token(data={"sub": username})
    refresh_token = auth.create_refresh_token(data={"sub": username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/password-reset-request")
def password_reset_request(
    request: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == request.email).first()
    if user:

        reset_token = generate_reset_token()
        
        # Create reset token in database
        db_token = models.PasswordResetToken(
            token=reset_token,
            user_id=user.id
        )
        db.add(db_token)
        db.commit()
        
    
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a reset link has been sent"}

@router.post("/password-reset")
def password_reset(reset_data: schemas.PasswordReset, db: Session = Depends(get_db)):
    
    reset_token = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == reset_data.token,
        models.PasswordResetToken.used == False,
        models.PasswordResetToken.expires_at > datetime.utcnow()
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update user password
    reset_token.user.hashed_password = auth.get_password_hash(reset_data.new_password)
    reset_token.used = True
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
def logout(current_user: models.User = Depends(get_current_user)):

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
