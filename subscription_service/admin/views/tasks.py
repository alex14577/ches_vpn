from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, or_, cast, String

from common.db import db_call
from common.models import Task

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    q: Optional[str] = None,
    status: Optional[str] = None,
    type: Optional[str] = None,
) -> HTMLResponse:
    """
    Read-only tasks list.

    Filters:
    - q: task id (uuid) / idempotency_key (substring)
    - status: pending / running / done / failed
    - type: exact match (string)

    Note: we do not filter by user_id here because your current Task model
    (as shown earlier) does not have user_id.
    """
    q = (q or "").strip()
    status = (status or "").strip()
    type = (type or "").strip()

    async def _load(db):
        stmt = select(Task).order_by(Task.created_at.desc())

        if status:
            stmt = stmt.where(Task.status == status)

        if type:
            stmt = stmt.where(Task.type == type)

        if q:
            conds = []
            # UUID search
            try:
                tid = uuid.UUID(q)
                conds.append(Task.id == tid)
            except Exception:
                pass

            like = f"%{q}%"
            conds.append(Task.idempotency_key.ilike(like))
            # payload is JSONB; cast to text for search (can be slow, but ok for admin)
            conds.append(cast(Task.payload, String).ilike(like))

            stmt = stmt.where(or_(*conds))

        res = await db._s.execute(stmt)
        return list(res.scalars().all())

    tasks = await db_call(_load)

    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": tasks, "q": q, "status": status, "type": type},
    )

@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page(request: Request, task_id: uuid.UUID) -> HTMLResponse:
    async def _load(db):
        res = await db._s.execute(select(Task).where(Task.id == task_id))
        return res.scalar_one_or_none()

    task = await db_call(_load)
    if task is None:
        return RedirectResponse(url="/admin/tasks", status_code=303)

    return templates.TemplateResponse(
        "task_detail.html",
        {"request": request, "task": task},
    )