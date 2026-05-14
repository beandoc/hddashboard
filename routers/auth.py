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

@router.get("/change-password", response_class=HTMLResponse)
async def change_password_form(request: Request):
    from dependencies import get_user
    user = get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user, "error": None})

@router.post("/change-password")
async def change_password(
    request: Request,
    current_pw: str = Form(...),
    new_pw: str = Form(...),
    confirm_pw: str = Form(...),
    db: Session = Depends(get_db),
):
    from config import pwd_context, serializer
    from dependencies import get_user
    user = get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    error = None

    # ── Validate new password ─────────────────────────────────────────────────
    if new_pw != confirm_pw:
        error = "New passwords do not match."
    elif len(new_pw) < 6:
        error = "New password must be at least 6 characters."
    else:
        # Staff user
        if hasattr(user, "username"):
            db_user = db.query(User).filter(User.username == user.username).first()
            if not db_user or not pwd_context.verify(current_pw, db_user.hashed_password):
                error = "Current password is incorrect."
            else:
                db_user.hashed_password = pwd_context.hash(new_pw)
                db.commit()
                return RedirectResponse(url="/?msg=password_changed", status_code=303)
        # Patient user
        elif isinstance(user, dict) and user.get("role") == "patient":
            p = db.query(Patient).filter(Patient.id == user["id"]).first()
            if not p or not pwd_context.verify(current_pw, p.hashed_password):
                error = "Current password is incorrect."
            else:
                p.hashed_password = pwd_context.hash(new_pw)
                db.commit()
                return RedirectResponse(url="/patient/dashboard?msg=password_changed", status_code=303)
        else:
            error = "Unknown user type. Please log in again."

    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "user": user,
        "error": error
    })

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
