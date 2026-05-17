import os
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, TimestampSigner
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Load environment variables from .env file
load_dotenv()

# Auth Configuration
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# URLSafeTimedSerializer embeds a creation timestamp in the signature so
# max_age enforcement is server-side and survives browser cookie deletion.
serializer = URLSafeTimedSerializer(SECRET_KEY)
_csrf_signer = TimestampSigner(SECRET_KEY + "-csrf")

# Cookie security — set COOKIE_SECURE=true in production (HTTPS).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SESSION_MAX_AGE  = 8 * 60 * 60   # 8 h absolute hard limit
SESSION_IDLE_TTL = 30 * 60        # 30 min inactivity auto-logout

# Rate limiter — shared across all routers.
limiter = Limiter(key_func=get_remote_address)

# Templates
templates = Jinja2Templates(directory="templates")
