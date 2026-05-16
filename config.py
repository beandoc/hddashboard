import os
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, TimestampSigner
from fastapi.templating import Jinja2Templates

# Auth Configuration
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(SECRET_KEY)
_csrf_signer = TimestampSigner(SECRET_KEY + "-csrf")

# Cookie security — set COOKIE_SECURE=true in production (HTTPS).
# Omit or set to "false" for local HTTP development.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours in seconds

# Templates
templates = Jinja2Templates(directory="templates")
