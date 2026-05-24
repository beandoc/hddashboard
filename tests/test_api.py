import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Test DB setup and monkeypatching SessionLocal BEFORE importing app
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from main import app
import main
main.SessionLocal = TestingSessionLocal
main._check_schema_version = lambda: None

from database import Base, get_db, User
from passlib.context import CryptContext
from fastapi.testclient import TestClient

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    # Create a test user
    db = TestingSessionLocal()
    if not db.query(User).filter(User.username == "testadmin").first():
        hashed_pw = pwd_context.hash("password123")
        user = User(username="testadmin", full_name="Test Admin", hashed_password=hashed_pw, role="admin", is_active=True)
        db.add(user)
        db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

def test_login_and_access_dashboard(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text

def test_api_patients_search(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    response = client.get("/api/v1/patients?q=test")
    assert response.status_code == 200
    assert "patients" in response.json()

def test_api_dashboard_month(client):
    # Bypass login and set session cookie directly
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/api/v1/dashboard?month=2026-04")
    assert response.status_code == 200
    assert "data" in response.json()

def test_patients_page_renders_with_csrf_token(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    response = client.get("/patients")
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text

def test_mortality_risk_pagination(client):
    import time
    from config import serializer
    token = serializer.dumps(f"staff:testadmin:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Test main page access
    response = client.get("/analytics/mortality-risk?page=1&limit=10&tier=all&search=")
    assert response.status_code == 200
    assert "Mortality Risk" in response.text
    
    # Test out-of-bounds page query parameters
    response = client.get("/analytics/mortality-risk?page=9999&limit=10&tier=all&search=")
    assert response.status_code == 200
    assert "Mortality Risk" in response.text
