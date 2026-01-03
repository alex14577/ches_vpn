from fastapi import Request
from .auth import require_admin

def require_admin_dep(request: Request) -> None:
    require_admin(request)