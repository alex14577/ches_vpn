from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import set_session_cookie, clear_session_cookie
from .deps import require_admin_dep

from .admin_auth import verify_password, save_admin_credentials

from .views.servers import router as servers_router
from .views.users import router as users_router
from .views.plans import router as plans_router
from .views.subscriptions import router as subs_router
from .views.stats import router as stats_router

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


@admin_router.get(
    "/password",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin_dep)],
)
async def password_page(request: Request):
    return templates.TemplateResponse(
        "admin_password.html",
        {"request": request, "title": "Change password"},
    )


@admin_router.post(
    "/password",
    dependencies=[Depends(require_admin_dep)],
)
async def password_change(
    request: Request,
    current_username: str = Form(...),
    current_password: str = Form(...),
    new_username: str = Form(...),
    new_password: str = Form(...),
    new_password2: str = Form(...),
):
    if not verify_password(current_username, current_password):
        return RedirectResponse(url="/admin/password?err=bad_current", status_code=303)

    if new_password != new_password2:
        return RedirectResponse(url="/admin/password?err=mismatch", status_code=303)

    if len(new_username.strip()) < 1 or len(new_password) < 4:
        return RedirectResponse(url="/admin/password?err=weak", status_code=303)

    save_admin_credentials(new_username.strip(), new_password)
    return RedirectResponse(url="/admin/password?ok=1", status_code=303)


# Protected pages
admin_router.include_router(servers_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(users_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(plans_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(subs_router, dependencies=[Depends(require_admin_dep)])
admin_router.include_router(stats_router, dependencies=[Depends(require_admin_dep)])
