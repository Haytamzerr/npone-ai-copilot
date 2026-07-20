"""
utils/deps.py
---------------
Shared FastAPI dependencies (auth guard for admin routes).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=True)


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Validates the JWT Bearer token on every /admin/* route."""
    username = decode_access_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
