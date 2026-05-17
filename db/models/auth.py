from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

from db.engine import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String, unique=True, index=True, nullable=False)
    full_name       = Column(String)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, default="staff")  # admin / doctor / staff
    is_active       = Column(Boolean, default=True)
    last_login      = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # TOTP MFA — required for admin and doctor roles.
    mfa_secret      = Column(String, nullable=True)
    mfa_enabled     = Column(Boolean, default=False, nullable=False)
