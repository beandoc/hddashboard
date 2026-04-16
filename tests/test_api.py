import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import Base, get_db, User
from passlib.context import CryptContext

# Test DB setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_api.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    # Perform login
    response = client.post("/login", data={"username": "testadmin", "password": "password123"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Dashboard" in response.text

def test_api_patients_search(client):
    # Need to be logged in for session cookie
    client.post("/login", data={"username": "testadmin", "password": "password123"})
    
    response = client.get("/api/patients?q=test")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_api_dashboard_month(client):
    client.post("/login", data={"username": "testadmin", "password": "password123"})
    response = client.get("/api/dashboard?month=2026-04")
    assert response.status_code == 200
    assert "metrics" in response.json()
