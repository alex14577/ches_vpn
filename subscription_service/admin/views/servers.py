import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from common.db import db_call
from common.models import VpnServer
from common.xui_client.registry import Manager

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

@router.get("/servers", response_class=HTMLResponse)
async def servers_page(request: Request):
    servers = await db_call(lambda db: db.servers.all())
    return templates.TemplateResponse("servers.html", {"request": request, "servers": servers})

@router.post("/servers/create")
async def servers_create(
    request: Request,
    code: str = Form(...),
    api_base_url: str = Form(...),
    api_username: str = Form(...),
    api_password: str = Form(...),
):
    server = VpnServer(
        code=code.strip(),
        api_base_url=api_base_url.strip(),
        api_username=api_username.strip(),
        api_password=api_password,
    )

    server = await db_call(lambda db: db.servers.create(server))
    users = await db_call(lambda db: db.users.active_subscription_users())

    serverManager: Manager = request.app.state.serverManager

    try:
        serverManager: Manager = request.app.state.serverManager
        await serverManager.syncServers()
    except Exception:
        return RedirectResponse("/admin/users?err=Не удалось синронизировать сервера из бд", status_code=303)

    for user in users:
        await serverManager.syncUser(user)

    return RedirectResponse(url="/admin/servers", status_code=303)

@router.post("/servers/{server_id}/delete")
async def servers_delete(
    request: Request,
    server_id: uuid.UUID
):
    await db_call(lambda db: db.servers.delete(server_id))
    
    try:
        serverManager: Manager = request.app.state.serverManager
        await serverManager.syncServers()
    except Exception:
        return RedirectResponse("/admin/users?err=Не удалось синронизировать сервера из бд", status_code=303)
    
    return RedirectResponse(url="/admin/servers", status_code=303)