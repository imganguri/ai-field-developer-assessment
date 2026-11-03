"""Constant-time verification for configured development bearer tokens."""
from __future__ import annotations
import hmac, os
from fastapi import HTTPException

def role_for_token(token: str | None) -> str:
    if not token:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    known = {"admin": os.getenv("ADMIN_TOKEN", "dev-admin-token"), "viewer": os.getenv("VIEWER_TOKEN", "dev-viewer-token")}
    for role, candidate in known.items():
        if candidate and hmac.compare_digest(token.encode(), candidate.encode()):
            return role
    raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
