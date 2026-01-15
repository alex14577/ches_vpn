from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import uuid

from sqlalchemy import select, or_, update

from common.db import db_call
from common.models import Subscription, SubscriptionStatus, User, Plan

def _parse_dt_local(s: str | None) -> datetime | None:
    if not s:
        return None
    # формат типа: 2026-01-02T13:45
    dt = datetime.fromisoformat(s)
    # трактуем как UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

@router.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request, q: Optional[str] = None, status: Optional[str] = None):
    q = (q or "").strip()
    status = (status or "").strip()

    async def _load(db):
        plans = await db.plans.active()

        stmt = (
            select(Subscription, User, Plan)
            .join(User, Subscription.user_id == User.id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .order_by(Subscription.created_at.desc())
        )

        if status:
            stmt = stmt.where(Subscription.status == status)

        if q:
            like = f"%{q}%"
            conds = []
            if q.isdigit():
                conds.append(User.tg_user_id == int(q))
            conds.append(User.username.ilike(like))
            conds.append(Plan.code.ilike(like))
            stmt = stmt.where(or_(*conds))

        res = await db._s.execute(stmt)
        rows = res.all()
        out = [{"subscription": sub, "user": user, "plan": plan} for (sub, user, plan) in rows]
        return plans, out

    plans, rows = await db_call(_load)

    return templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "rows": rows,
            "plans": plans,
            "q": q,
            "status": status,
            "err": request.query_params.get("err"),
            "ok": request.query_params.get("ok"),
        },
    )


@router.post("/subscriptions/create")
async def subscriptions_create(
    user_query: str = Form(...),
    plan_id: uuid.UUID = Form(...),
):
    user_query = (user_query or "").strip()

    async def _create(db) -> tuple[bool, str]:
        # 1) resolve user
        user: User | None = None
        if user_query.isdigit():
            user = await db.users.byTgId(int(user_query))
        if user is None:
            # exact username
            res = await db._s.execute(select(User).where(User.username == user_query))
            user = res.scalar_one_or_none()

        if user is None:
            return False, "Пользователь не найден"

        # 2) plan check
        res = await db._s.execute(select(Plan).where(Plan.id == plan_id))
        plan = res.scalar_one_or_none()
        if plan is None:
            return False, "План не найден"
        if not plan.is_active:
            return False, "План не активен"

        # 3) compute start from last subscription end
        now = datetime.now(timezone.utc)
        last = await db.subscriptions.last_for_user(user.id)

        start = now
        if last is not None and last.valid_until is not None:
            start = max(now, last.valid_until)
        elif last is not None and last.valid_until is None:
            return False, "У пользователя уже есть бессрочная подписка"

        # 4) compute end
        end = None
        if plan.duration_days is not None:
            end = start + timedelta(days=int(plan.duration_days))

        # 5) insert
        await db.subscriptions.add(user_id=user.id, plan_id=plan.id, valid_from=start, valid_until=end)
        return True, "ok"

    ok, msg = await db_call(_create)
    if not ok:
        return RedirectResponse("/admin/subscriptions?err=" + quote(msg), status_code=303)
    return RedirectResponse("/admin/subscriptions?ok=1", status_code=303)

@router.get("/subscriptions/{sub_id}", response_class=HTMLResponse)
async def subscription_edit_page(request: Request, sub_id: uuid.UUID):
    async def _load(db):
        res = await db._s.execute(
            select(Subscription, User, Plan)
            .join(User, Subscription.user_id == User.id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.id == sub_id)
        )
        row = res.first()
        if not row:
            return None
        sub, user, plan = row
        return {"subscription": sub, "user": user, "plan": plan}

    ctx = await db_call(_load)
    if ctx is None:
        return RedirectResponse("/admin/subscriptions?err=" + quote("Подписка не найдена"), status_code=303)

    return templates.TemplateResponse(
        "subscription_edit.html",
        {"request": request, **ctx, "err": request.query_params.get("err"), "ok": request.query_params.get("ok")},
    )
    
@router.post("/subscriptions/{sub_id}/update")
async def subscription_update(
    sub_id: uuid.UUID,
    valid_from: str = Form(...),
    valid_until: Optional[str] = Form(default=None),
    status: str = Form(...),
):
    vf = _parse_dt_local(valid_from)
    vu = _parse_dt_local(valid_until) if (valid_until or "").strip() else None

    if vf is None:
        return RedirectResponse(f"/admin/subscriptions/{sub_id}?err=" + quote("valid_from обязателен"), status_code=303)

    allowed_statuses = {s.value for s in SubscriptionStatus}
    if status not in allowed_statuses:
        return RedirectResponse(f"/admin/subscriptions/{sub_id}?err=" + quote("Некорректный статус"), status_code=303)

    async def _upd(db) -> bool:
        res = await db._s.execute(select(Subscription).where(Subscription.id == sub_id))
        sub: Subscription = res.scalar_one_or_none()
        if sub is None:
            return False

        stmt = (
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(
                valid_from=vf,
                valid_until=vu,
                status=status,
            )
        )
        res = await db._s.execute(stmt)
        await db._s.flush()

        return (res.rowcount or 0) > 0

    ok = await db_call(_upd)
    if not ok:
        return RedirectResponse("/admin/subscriptions?err=" + quote("Подписка не найдена"), status_code=303)

    return RedirectResponse(f"/admin/subscriptions/{sub_id}?ok=1", status_code=303)

@router.post("/subscriptions/{sub_id}/delete")
async def subscription_delete(sub_id: uuid.UUID):
    async def _del(db) -> bool:
        res = await db._s.execute(select(Subscription).where(Subscription.id == sub_id))
        sub = res.scalar_one_or_none()
        if sub is None:
            return False
        await db._s.delete(sub)
        return True

    ok = await db_call(_del)
    if not ok:
        return RedirectResponse("/admin/subscriptions?err=" + quote("Подписка не найдена"), status_code=303)

    return RedirectResponse("/admin/subscriptions?ok=deleted", status_code=303)
