import time

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from itsdangerous import BadData

from database import get_db, User, Patient, PatientCredentials
from config import templates, serializer, _csrf_signer, COOKIE_SECURE, SESSION_MAX_AGE, limiter

router = APIRouter()

_HARDCODED_PASSWORD = "chsc"
_STAFF_ROLES = {"admin", "staff", "doctor"}

from pydantic import BaseModel
from fastapi import Response

class LoginPayload(BaseModel):
    username: str
    password: str

@router.post("/api/login")
async def api_login(
    payload: LoginPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    now_ts = int(time.time())
    username = payload.username
    password = payload.password

    from config import pwd_context as _pwd
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user:
        _hash = getattr(user, "hashed_password", None)
        _ok = _pwd.verify(password, _hash) if _hash else (password == _HARDCODED_PASSWORD)
        if _ok:
            if not _hash and password == _HARDCODED_PASSWORD:
                user.hashed_password = _pwd.hash(password)
            user.last_login = datetime.utcnow()
            db.commit()
            token = serializer.dumps(f"staff:{user.username}:{now_ts}")
            response.set_cookie(
                key="hd_session", value=token,
                httponly=True, secure=COOKIE_SECURE,
                samesite="strict", max_age=SESSION_MAX_AGE,
            )
            return {"access_token": "ok", "message": "Login successful"}

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    csrf_token = _csrf_signer.sign("login").decode()
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "csrf_token": csrf_token})


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")

    now_ts = int(time.time())

    # 1. Staff — verify bcrypt hash if set, else fall back to shared passphrase
    from config import pwd_context as _pwd
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user:
        _hash = getattr(user, "hashed_password", None)
        _ok = _pwd.verify(password, _hash) if _hash else (password == _HARDCODED_PASSWORD)
        if _ok:
            # Opportunistically hash the shared passphrase on first use
            if not _hash and password == _HARDCODED_PASSWORD:
                user.hashed_password = _pwd.hash(password)
            user.last_login = datetime.utcnow()
            db.commit()
            token = serializer.dumps(f"staff:{user.username}:{now_ts}")
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie(
                key="hd_session", value=token,
                httponly=True, secure=COOKIE_SECURE,
                samesite="strict", max_age=SESSION_MAX_AGE,
            )
            return response

    # 2. Patient portal — join PatientCredentials
    from config import pwd_context
    p = (
        db.query(Patient)
        .join(PatientCredentials, Patient.id == PatientCredentials.patient_id, isouter=False)
        .filter(PatientCredentials.login_username == username.lower(), Patient.is_active == True)
        .first()
    )

    # Auto-provision on first login with first name + "chsc"
    if not p and password == _HARDCODED_PASSWORD:
        for candidate in db.query(Patient).filter(Patient.is_active == True).all():
            first_name = candidate.name.split()[0].lower()
            if first_name == username.lower() and not candidate.login_username:
                candidate.login_username = first_name
                candidate.hashed_password = pwd_context.hash(_HARDCODED_PASSWORD)
                db.commit()
                p = candidate
                break

    if p and (password == _HARDCODED_PASSWORD or pwd_context.verify(password, p.hashed_password)):
        token = serializer.dumps(f"patient:{p.login_username}:{now_ts}")
        response = RedirectResponse(url="/patient/dashboard", status_code=303)
        response.set_cookie(
            key="hd_session", value=token,
            httponly=True, secure=COOKIE_SECURE,
            samesite="strict", max_age=SESSION_MAX_AGE,
        )
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
    csrf_token = _csrf_signer.sign("change-password").decode()
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user, "error": None, "csrf_token": csrf_token})


@router.post("/change-password")
async def change_password(
    request: Request,
    current_pw: str = Form(...),
    new_pw: str = Form(...),
    confirm_pw: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")
    from config import pwd_context
    from dependencies import get_user
    user = get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    error = None
    if new_pw != confirm_pw:
        error = "New passwords do not match."
    elif len(new_pw) < 6:
        error = "New password must be at least 6 characters."
    else:
        if hasattr(user, "username"):
            db_user = db.query(User).filter(User.username == user.username).first()
            if not db_user:
                error = "Current password is incorrect."
            else:
                _hash = getattr(db_user, "hashed_password", None)
                _ok = pwd_context.verify(current_pw, _hash) if _hash else (current_pw == _HARDCODED_PASSWORD)
                if not _ok:
                    error = "Current password is incorrect."
                else:
                    db_user.hashed_password = pwd_context.hash(new_pw)
                    db.commit()
                    return RedirectResponse(url="/?msg=password_changed", status_code=303)
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
        "request": request, "user": user, "error": error,
    })


async def _me_response(request: Request):
    from dependencies import get_user
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if isinstance(user, dict):
        return {"username": user["username"], "full_name": user["full_name"], "role": user["role"]}
    return {"username": user.username, "full_name": user.full_name, "role": user.role}


@router.get("/api/v1/me")
async def get_current_user_api_v1(request: Request):
    return await _me_response(request)


@router.get("/api/me")
async def get_current_user_api_legacy(request: Request):
    return RedirectResponse(url="/api/v1/me", status_code=301)
