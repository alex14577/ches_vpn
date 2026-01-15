# subscription_service/admin/views/plans.py

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, delete, or_
from sqlalchemy.exc import IntegrityError

from common.db import db_call
from common.models import Plan

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")


@router.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request, q: Optional[str] = None) -> HTMLResponse:
    q = (q or "").strip()

    async def _load(db):
        stmt = select(Plan).order_by(Plan.created_at.desc())
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Plan.code.ilike(like), Plan.title.ilike(like)))
        res = await db._s.execute(stmt)
        return list(res.scalars().all())

    plans = await db_call(_load)

    return templates.TemplateResponse(
        "plans.html",
        {"request": request, "plans": plans, "q": q},
    )


@router.post("/plans/create")
async def plan_create(
    code: str = Form(...),
    title: str = Form(...),
    price_rub: int = Form(...),
    duration_days: Optional[str] = Form(default=None),  # из формы приходит строка
    is_active: Optional[str] = Form(default=None),      # checkbox -> "on" или None
):
    code = code.strip()
    title = title.strip()

    dd = (duration_days or "").strip()
    duration_val = int(dd) if dd else None
    active_val = bool(is_active)  # если чекбокс отмечен, приходит "on"

    plan = Plan(
        code=code,
        title=title,
        price_rub=int(price_rub),
        duration_days=duration_val,
        is_active=active_val,
    )

    async def _create(db):
        exists_stmt = select(Plan.id).where(Plan.code.ilike(code)).limit(1)
        res = await db._s.execute(exists_stmt)
        if res.scalar_one_or_none() is not None:
            raise ValueError("План с таким кодом уже существует.")
        db._s.add(plan)
        await db._s.flush()

    try:
        await db_call(_create)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/plans?err={exc}", status_code=303)
    except IntegrityError:
        return RedirectResponse(url="/admin/plans?err=План с таким кодом уже существует.", status_code=303)
    return RedirectResponse(url="/admin/plans", status_code=303)


@router.get("/plans/{plan_id}", response_class=HTMLResponse)
async def plan_edit_page(request: Request, plan_id: uuid.UUID) -> HTMLResponse:
    async def _load(db):
        res = await db._s.execute(select(Plan).where(Plan.id == plan_id))
        return res.scalar_one_or_none()

    plan = await db_call(_load)
    if plan is None:
        return RedirectResponse(url="/admin/plans", status_code=303)

    return templates.TemplateResponse(
        "plan_edit.html",
        {"request": request, "plan": plan},
    )


@router.post("/plans/{plan_id}/update")
async def plan_update(
    plan_id: uuid.UUID,
    title: str = Form(...),
    price_rub: int = Form(...),
    duration_days: Optional[str] = Form(default=None),
    is_active: Optional[str] = Form(default=None),
):
    title = title.strip()

    dd = (duration_days or "").strip()
    duration_val = int(dd) if dd else None
    active_val = bool(is_active)

    async def _upd(db):
        stmt = (
            update(Plan)
            .where(Plan.id == plan_id)
            .values(
                title=title,
                price_rub=int(price_rub),
                duration_days=duration_val,
                is_active=active_val,
            )
        )
        await db._s.execute(stmt)

    await db_call(_upd)
    return RedirectResponse(url=f"/admin/plans/{plan_id}", status_code=303)


@router.post("/plans/{plan_id}/delete")
async def plan_delete(plan_id: uuid.UUID):
    async def _del(db):
        # Если есть subscriptions с ondelete=RESTRICT, БД не даст удалить — это ок.
        await db._s.execute(delete(Plan).where(Plan.id == plan_id))

    await db_call(_del)
    return RedirectResponse(url="/admin/plans", status_code=303)
