from datetime import timedelta

from app import auth, models


def test_registration_and_login(client, registered_user):
    response = client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_invalid_login(client, registered_user):
    response = client.post("/api/users/login", json={"username": "alex", "password": "wrong"})
    assert response.status_code == 401


def test_protected_route_requires_auth(client):
    assert client.get("/api/users/me").status_code == 401


def test_inactive_user_cannot_login(client, registered_user, db_session):
    user = db_session.query(models.User).filter_by(username="alex").one()
    user.is_active = False
    db_session.commit()
    assert client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"}).status_code == 401


def test_expired_token_is_rejected(client, registered_user):
    token = auth.create_access_token({"sub": "alex"}, expires_delta=timedelta(seconds=-1))
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
