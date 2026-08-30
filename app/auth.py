from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
import secrets
from typing import Optional, Dict, Any
import os

# Secret key for JWT tokens - In production, use environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
REFRESH_SECRET_KEY = os.getenv("REFRESH_JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# Password hashing context - using both argon2 and bcrypt for compatibility
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"], 
    deprecated="auto",
    argon2__memory_cost=65536,  # 64MB memory
    argon2__time_cost=3,         # 3 iterations
    argon2__parallelism=4        # 4 threads
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """
    Hash a password with proper length handling
    """
    # Argon2 has a password length limit, truncate if too long
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    """
    to_encode = data.copy()
    
    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add claims
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iat": datetime.utcnow()  # Issued at
    })
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        print(f"Error creating access token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create access token"
        )

def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT refresh token
    """
    to_encode = data.copy()
    
    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Add claims
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.utcnow()
    })
    
    try:
        encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        print(f"Error creating refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create refresh token"
        )

def verify_token(token: str, is_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Verify a JWT token and return payload if valid
    """
    try:
        # Choose the appropriate secret key
        secret_key = REFRESH_SECRET_KEY if is_refresh else SECRET_KEY
        
        # Decode and verify token
        payload = jwt.decode(
            token, 
            secret_key, 
            algorithms=[ALGORITHM],
            options={"verify_exp": True}
        )
        
        # Verify token type
        token_type = payload.get("type")
        expected_type = "refresh" if is_refresh else "access"
        
        if token_type != expected_type:
            print(f"Invalid token type: expected {expected_type}, got {token_type}")
            return None
        
        return payload
        
    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return None
    except jwt.JWTError as e:
        print(f"JWT verification error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected token verification error: {e}")
        return None

def refresh_access_token(refresh_token: str) -> Optional[str]:
    """
    Create a new access token using a valid refresh token
    """
    # Verify the refresh token
    payload = verify_token(refresh_token, is_refresh=True)
    
    if not payload:
        return None
    
    # Extract user data from payload
    username = payload.get("sub")
    if not username:
        return None
    
    # Create new access token
    try:
        new_access_token = create_access_token(data={"sub": username})
        return new_access_token
    except Exception as e:
        print(f"Error refreshing access token: {e}")
        return None

def decode_token(token: str, is_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Decode token without verification (use for debugging only)
    """
    try:
        secret_key = REFRESH_SECRET_KEY if is_refresh else SECRET_KEY
        payload = jwt.decode(
            token, 
            secret_key, 
            algorithms=[ALGORITHM],
            options={"verify_exp": False, "verify_signature": False}
        )
        return payload
    except Exception as e:
        print(f"Token decode error: {e}")
        return None

def get_token_expiration(token: str, is_refresh: bool = False) -> Optional[datetime]:
    """
    Get token expiration datetime
    """
    payload = decode_token(token, is_refresh)
    if payload and "exp" in payload:
        return datetime.fromtimestamp(payload["exp"])
    return None

def is_token_expired(token: str, is_refresh: bool = False) -> bool:
    """
    Check if token is expired
    """
    exp = get_token_expiration(token, is_refresh)
    if exp:
        return datetime.utcnow() > exp
    return True  # If we can't get expiration, assume it's expired

def get_token_remaining_time(token: str, is_refresh: bool = False) -> Optional[timedelta]:
    """
    Get remaining time for token
    """
    exp = get_token_expiration(token, is_refresh)
    if exp:
        remaining = exp - datetime.utcnow()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)
    return None

# For debugging - print configuration on import
print(f"🔐 Auth module initialized with:")
print(f"   - Algorithm: {ALGORITHM}")
print(f"   - Access token expiry: {ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
print(f"   - Refresh token expiry: {REFRESH_TOKEN_EXPIRE_DAYS} days")
print(f"   - Password hashing: Argon2 + BCrypt")