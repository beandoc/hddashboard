from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os

# These will be imported from main or other central modules
# For now, we'll assume they are available or we'll pass them in
from database import get_db, User, Patient
# We need to reach back to main for these, which is a bit circular.
# A better way is to move these to a shared config.py.

from config import templates

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    from config import pwd_context, serializer, templates
    
    # 1. Try Staff table
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user and pwd_context.verify(password, user.hashed_password):
        user.last_login = datetime.utcnow()
        db.commit()
        token = serializer.dumps(f"staff:{user.username}")
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="hd_session", value=token, httponly=True)
        return response

    # 2. Try Patient table
    p = db.query(Patient).filter(Patient.login_username == username.lower(), Patient.is_active == True).first()
    
    # Auto-provision logic if user asked for "first name / chsc"
    if not p and password == "chsc":
        all_patients = db.query(Patient).filter(Patient.is_active == True).all()
        for candidate in all_patients:
            first_name = candidate.name.split()[0].lower()
            if first_name == username.lower() and not candidate.login_username:
                candidate.login_username = first_name
                candidate.hashed_password = pwd_context.hash("chsc")
                db.commit()
                p = candidate
                break

    if p and pwd_context.verify(password, p.hashed_password):
        token = serializer.dumps(f"patient:{p.login_username}")
        response = RedirectResponse(url="/patient/dashboard", status_code=303)
        response.set_cookie(key="hd_session", value=token, httponly=True)
        return response

    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("hd_session")
    return response

@router.get("/api/me")
async def get_current_user_api(request: Request):
    # This still refers to main.py's get_user. 
    # In a full refactor, get_user would be in a dependencies.py or shared module.
    from dependencies import get_user
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if isinstance(user, dict): # Patient
        return {"username": user["username"], "full_name": user["full_name"], "role": user["role"]}
    return {"username": user.username, "full_name": user.full_name, "role": user.role}
