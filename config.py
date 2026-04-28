import os
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, TimestampSigner
from fastapi.templating import Jinja2Templates

# Auth Configuration
SECRET_KEY = os.environ.get("SECRET_KEY", "HD_DASHBOARD_SECRET_SECURE_2026")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(SECRET_KEY)
_csrf_signer = TimestampSigner(SECRET_KEY + "-csrf")

# Templates
templates = Jinja2Templates(directory="templates")
