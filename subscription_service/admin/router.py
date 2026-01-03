from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import verify_password, set_session_cookie, clear_session_cookie
from .deps import require_admin_dep

from .views.servers import router as servers_router
from .views.users import router as users_router
from .views.plans import router as plans_router
from .views.subscriptions import router as subs_router
from .views.tasks import router as tasks_router

templates = Jinja2Templates(directory="subscription_service/admin/templates")

admin_router = APIRouter()

@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    err = request.query_params.get("err")
    return templates.TemplateResponse("login.html", {"request": request, "err": err})

@admin_router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if not verify_password(username, password):
        return RedirectResponse(url="/admin/login?err=1", status_code=303)

    resp = RedirectResponse(url="/admin/servers", status_code=303)
    set_session_cookie(resp)
    return resp

@admin_router.post("/logout")
async def logout():
    resp = RedirectResponse(url="/admin/login", status_code=303)
    clear_session_cookie(resp)
    return resp

# Protected pages
admin_router.include_router(servers_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(users_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(plans_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(subs_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(tasks_router, dependencies=[Depends(require_admin_dep)])