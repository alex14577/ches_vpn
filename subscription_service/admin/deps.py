from fastapi import Request
from fastapi.responses import RedirectResponse
from .auth import COOKIE_NAME

def require_admin_dep(request: Request):
    if not request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/admin/login", status_code=303)
    return None