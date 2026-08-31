from sqlalchemy.orm import Session

from .. import models
from ..auth import get_password_hash, verify_password


def find_existing_user(db: Session, username: str, email: str):
    return db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()


def create_user(db: Session, username: str, email: str, password: str) -> models.User:
    user = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, identifier: str, password: str):
    user = db.query(models.User).filter(
        (models.User.username == identifier) | (models.User.email == identifier)
    ).first()
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user
