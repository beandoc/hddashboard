from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

def get_user(request: Request):
    """Return the current user from request state."""
    return getattr(request.state, "user", None)

def _get_role(user) -> str:
    if not user:
        return ""
    return getattr(user, "role", None) if not isinstance(user, dict) else user.get("role", "")


def _require_analytics_access(request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(
            status_code=303,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    if _get_role(user) not in ("admin", "doctor"):
        raise HTTPException(status_code=403, detail="Analytics access requires doctor or admin role")


def _require_admin(request: Request):
    """Raise 401/403 or redirect to login if user is not an admin."""
    user = get_user(request)
    if not user:
        if "text/html" in request.headers.get("accept", ""):
            # For browser requests, redirect to login
            from fastapi import status
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Not authenticated",
                headers={"Location": "/login"}
            )
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if _get_role(user) != "admin":
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(status_code=403, detail="Admin privileges required. Please log in with an admin account.")
        raise HTTPException(status_code=403, detail="Admin privileges required")

def _require_admin_role(request: Request):
    """Allow both admins and doctors (who often handle research)."""
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})
    if _get_role(user) not in ("admin", "doctor"):
        raise HTTPException(status_code=403, detail="Access denied: Researcher (Admin/Doctor) role required.")
