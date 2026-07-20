"""
utils/security.py
-------------------
Security controls layered with the prompt-level rules in prompts/system_prompt.py
(defense in depth). None of these controls alone is sufficient; together they
substantially raise the cost of abuse.

Includes:
    - HTML/XSS sanitization of any user text that might later be rendered.
    - A lightweight prompt-injection heuristic filter (belt-and-suspenders on
      top of the system prompt's own "ignore embedded instructions" rule).
    - JWT-based auth for admin dashboard routes.
    - Password hashing (bcrypt via passlib) -- no admin password stored
      in plaintext, ever.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import bleach
from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Heuristic patterns commonly seen in prompt-injection attempts. This is a
# defense-in-depth signal (logged + optionally blocked), not a silver bullet.
_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|above) instructions",
    r"you are now",
    r"disregard (the|your) (system|previous) prompt",
    r"reveal (your|the) (system prompt|instructions)",
    r"act as (if|a) (developer|admin|root)",
    r"</?system>",
    r"jailbreak",
]
_injection_re = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_text(raw: str) -> str:
    """Strip HTML/script content from user-supplied text to prevent stored XSS."""
    return bleach.clean(raw, tags=[], attributes={}, strip=True).strip()


def looks_like_prompt_injection(text: str) -> bool:
    return bool(_injection_re.search(text))


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None
