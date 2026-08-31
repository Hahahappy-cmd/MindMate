from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from . import models
from .auth import verify_token
from typing import Optional
import logging
import secrets

logger = logging.getLogger(__name__)

class OptionalHTTPBearer(HTTPBearer):
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        try:
            return await super().__call__(request)
        except HTTPException:
            return None

security = OptionalHTTPBearer(auto_error=False)

def require_csrf(request: Request) -> None:
    """Protect cookie-authenticated state changes; bearer API clients are exempt."""
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

def get_token_from_request(request: Request) -> Optional[str]:
    """
    Extract token from either Authorization header or cookie
    """
    # Try to get from Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return auth_header
    
    # Try to get from cookie
    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        if token_cookie.startswith("Bearer "):
            return token_cookie[7:]
        return token_cookie
    
    return None

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Required authentication - raises 401 if no valid token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try to get token from either source
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = get_token_from_request(request)
    
    if not token:
        logger.warning("No credentials provided")
        raise credentials_exception
    
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = verify_token(token)
        if not payload:
            raise credentials_exception
        
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
        
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user or not user.is_active:
            raise credentials_exception
        
        return user if user and user.is_active else None
        
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise credentials_exception

def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Optional authentication - returns user if valid token, None otherwise
    """
    try:
        # Try to get token from either source
        token = None
        if credentials:
            token = credentials.credentials
        else:
            token = get_token_from_request(request)
        
        if not token:
            return None
        
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = verify_token(token)
        if not payload:
            return None
        
        username: str = payload.get("sub")
        if not username:
            return None
        
        user = db.query(models.User).filter(models.User.username == username).first()
        return user
        
    except Exception as e:
        logger.debug(f"Optional auth error: {e}")
        return None
