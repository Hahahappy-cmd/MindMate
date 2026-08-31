import secrets
import string
from datetime import datetime, timezone

def generate_reset_token(length=32):
    
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def is_token_expired(expires_at: datetime) -> bool:
    
    return datetime.now(timezone.utc) > expires_at

def validate_password_strength(password: str) -> bool:
    
    if len(password) < 8:
        return False
    return True
