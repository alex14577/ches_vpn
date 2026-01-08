from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, delete, or_, cast, String
from urllib.parse import quote

from common.db import db_call
from common.models import User
from common.xui_client.registry import Manager

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, q: Optional[str] = None) -> HTMLResponse:
    users, source_stats = await db_call(lambda db:  db.users.list_with_source_stats(q=q))

    return templates.TemplateResponse(
        "users.html",
        {"request": request, 
         "users": users, 
         "q": (q or "").strip(), 
         "source_stats": source_stats},
    )

@router.post("/users/create")
async def user_create(
    request: Request,
    tg_user_id: int = Form(...),
    username: Optional[str] = Form(default=None),
    refer_id: Optional[str] = Form(default=None),
):
    username = (username or "").strip() or None
    refer_id = (refer_id or "").strip() or None

    async def _create(db):
        # If user with this tg_user_id already exists: update basic fields.
        res = await db._s.execute(select(User).where(User.tg_user_id == int(tg_user_id)))
        user: User = res.scalar_one_or_none()

        if user is None:
            user = User(tg_user_id=int(tg_user_id), username=username, refer_id=refer_id)
            db._s.add(user)
            await db._s.flush()
        else:
            user.username = username
            user.refer_id = refer_id
            await db._s.flush()

        return user

    user = await db_call(_create)
    
    serverManager: Manager = request.app.state.serverManager
    await   serverManager.sync_user(user)
    return RedirectResponse(url=f"/admin/users/{user.id}", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_edit_page(request: Request, user_id: uuid.UUID) -> HTMLResponse:
    async def _load(db):
        res = await db._s.execute(select(User).where(User.id == user_id))
        return res.scalar_one_or_none()

    user = await db_call(_load)
    if user is None:
        return RedirectResponse(url="/admin/users", status_code=303)

    return templates.TemplateResponse("user_edit.html", {"request": request, "user": user})

@router.post("/users/{user_id}/update")
async def user_update(
    user_id: uuid.UUID,
    username: Optional[str] = Form(default=None),
    refer_id: Optional[str] = Form(default=None),
):
    username = (username or "").strip() or None
    refer_id = (refer_id or "").strip() or None

    user: User = await db_call(lambda db: db.users.get(user_id))
    if not user:
        return RedirectResponse(
            "/admin/users?err=Пользователь не найден",
            status_code=303,
        )

    user.refer_id = refer_id
    user.username = username
    user = await db_call(lambda db: db.users.update(user=user))
        
    # На серверах не меняем !!!!                   <=================================
    # try:
    #     serverManager: Manager = request.app.state.serverManager
    #     await serverManager.sync_user(user)
    # except Exception:
    #     return RedirectResponse("/admin/users?err=Не удалось обновить пользователя на VPN-серверах", status_code=303)
    # На серверах не меняем !!!!                   <=================================

    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/delete")
async def user_delete(request: Request, user_id: uuid.UUID):
    user = await db_call(lambda db: db.users.get(user_id))
    if user is None:
        return RedirectResponse("/admin/users?err=Пользователь не найден", status_code=303)

    serverManager: Manager = request.app.state.serverManager

    try:
        await serverManager.del_user(user)
    except Exception:
        return RedirectResponse("/admin/users?err=Не удалось удалить пользователя на VPN-серверах", status_code=303)

    ok = await db_call(lambda db: db.users.delete(user_id))
    if not ok:
        return RedirectResponse("/admin/users?err=Пользователь не найден", status_code=303)

    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/api/users/suggest")
async def users_suggest(q: str):
    q = (q or "").strip()

    async def _load(db):
        like = f"%{q}%"
        conds = [User.username.ilike(like)]

        if q.isdigit():
            # префикс по tg id
            conds.append(cast(User.tg_user_id, String).like(f"{q}%"))

        stmt = (
            select(User)
            .where(or_(*conds))
            .order_by(User.created_at.desc())
            .limit(10)
        )

        res = await db._s.execute(stmt)
        users = res.scalars().all()

        return [{"tg_user_id": u.tg_user_id, "username": u.username} for u in users]

    return JSONResponse(await db_call(_load))