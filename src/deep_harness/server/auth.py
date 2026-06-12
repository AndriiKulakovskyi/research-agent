"""Token auth: PBKDF2 password hashing, opaque bearer tokens stored hashed."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from deep_harness.server.db import AppDB

_PBKDF2_ITERATIONS = 200_000

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: str
    username: str


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register_user(db: AppDB, username: str, password: str) -> str:
    username = username.strip().lower()
    if len(username) < 3:
        raise HTTPException(400, "username must be at least 3 characters")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if db.get_user_by_username(username):
        raise HTTPException(409, "username already taken")
    salt = secrets.token_hex(16)
    return db.create_user(username, hash_password(password, salt), salt)


def issue_token(db: AppDB, username: str, password: str) -> str:
    row = db.get_user_by_username(username.strip().lower())
    if row is None or not hmac.compare_digest(
        row["password_hash"], hash_password(password, row["salt"])
    ):
        raise HTTPException(401, "invalid username or password")
    token = secrets.token_urlsafe(32)
    db.store_token(hash_token(token), row["id"])
    return token


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(401, "missing bearer token")
    db: AppDB = request.app.state.db
    user_id = db.get_user_id_for_token(hash_token(credentials.credentials))
    if user_id is None:
        raise HTTPException(401, "invalid or expired token")
    row = db.get_user(user_id)
    if row is None:
        raise HTTPException(401, "user no longer exists")
    return CurrentUser(id=row["id"], username=row["username"])
