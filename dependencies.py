from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

def get_user(request: Request):
    """Return the current user from request state."""
    return getattr(request.state, "user", None)

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
    
    # User can be a SQLAlchemy object (staff) or a dict (patient)
    role = getattr(user, "role", None) if not isinstance(user, dict) else user.get("role")
    if role != "admin":
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(status_code=403, detail="Admin privileges required. Please log in with an admin account.")
        raise HTTPException(status_code=403, detail="Admin privileges required")
