import pytest
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set up test database config before imports
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import database
database.SessionLocal = TestingSessionLocal

from main import app
import main
main.SessionLocal = TestingSessionLocal
main._check_schema_version = lambda: None

from database import Base, get_db
from passlib.context import CryptContext
from fastapi.testclient import TestClient
from config import serializer

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
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

def test_ecogreen_login_web(client):
    # Web login redirects (303) to sustainability page and sets hd_session cookie
    from config import _csrf_signer
    csrf_token = _csrf_signer.sign("login").decode()
    
    response = client.post(
        "/login",
        data={"username": "ecogreen", "password": "test1234", "csrf_token": csrf_token},
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers.get("location") == "/analytics/sustainability"
    assert "hd_session" in client.cookies

def test_ecogreen_login_api(client):
    # API login returns success JSON and sets hd_session cookie
    response = client.post(
        "/api/login",
        json={"username": "ecogreen", "password": "test1234"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "ok"
    assert "hd_session" in client.cookies

def test_ecogreen_restricted_access_html(client):
    # Log in as ecogreen
    token = serializer.dumps(f"ecogreen:ecogreen:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Try accessing root page - should redirect (302) to sustainability calculator
    response = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/analytics/sustainability"
    
    # Try accessing patients page - should redirect to sustainability
    response = client.get("/patients", headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/analytics/sustainability"

def test_ecogreen_restricted_access_api(client):
    # Log in as ecogreen
    token = serializer.dumps(f"ecogreen:ecogreen:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Try calling api endpoint - should return 403 Forbidden
    response = client.get("/api/v1/patients", headers={"accept": "application/json"})
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

def test_ecogreen_save_blocked(client):
    # Log in as ecogreen
    token = serializer.dumps(f"ecogreen:ecogreen:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Attempting to save sustainability parameters should fail with 403
    response = client.post(
        "/analytics/sustainability/save",
        data={
            "month_str": "2026-06",
            "electricity": 1200,
            "water": 45,
            "bio_waste": 150,
            "gen_waste": 80
        }
    )
    assert response.status_code == 403
    assert "Save operation disabled" in response.text

def test_ecogreen_sustainability_page_accessible(client):
    # Log in as ecogreen
    token = serializer.dumps(f"ecogreen:ecogreen:{int(time.time())}")
    client.cookies.set("hd_session", token)
    
    # Check page loads successfully
    response = client.get("/analytics/sustainability")
    assert response.status_code == 200
    assert "EcoRenal" in response.text
    # Verify the save button exists and is disabled
    assert 'class="btn-save"' in response.text
    assert "disabled" in response.text
