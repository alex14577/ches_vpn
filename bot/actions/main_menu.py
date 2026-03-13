from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from bot.actions import settings
from bot.actions.settings import PUBLIC_BASE_URL
from bot.helpers import helpers
from common.db import db_call
from common.models import Plan, Subscription, User
from sqlalchemy import select

HTML = ParseMode.HTML


def _make_connect_ref(subscription_token: str) -> str:
    return f"{PUBLIC_BASE_URL}/connect/{subscription_token}"


def _make_share_ref(connect_ref: str) -> str:
    return f"https://t.me/share/url?url={quote(connect_ref)}"


async def _get_user(tg_user_id: int, username: str | None, full_name: str | None = None) -> User:
    return await db_call(lambda db: db.users.getOrCreate(tg_user_id, username, full_name=full_name))


def _days_left(valid_until: datetime | None) -> str:
    if valid_until is None:
        return "без ограничений"
    now = datetime.now(timezone.utc)
    delta = (valid_until - now).total_seconds()
    days = max(0, int((delta + 86399) // 86400))
    return f"{days} дн."


async def _ensure_trial_subscription(user: User) -> None:
    async def _load(db) -> None:
        db_user = await db.users.get(user.id)
        if db_user is None:
            return
        active_sub = await db.subscriptions.active_for_user(user.id)
        if active_sub is not None:
            return

        if db_user.used_trial:
            return

        trial_plan = await db.plans.getByCode("trial")
        if trial_plan is None or not trial_plan.is_active:
            return

        now = datetime.now(timezone.utc)
        valid_until = None
        if trial_plan.duration_days is not None:
            valid_until = now + timedelta(days=int(trial_plan.duration_days))

        await db.subscriptions.add(
            user_id=user.id,
            plan_id=trial_plan.id,
            valid_from=now,
            valid_until=valid_until,
            expected_amount_minor=0,
            status="pending_payment",
        )
        db_user.used_trial = True
        await db._s.flush()

    await db_call(_load)


async def _get_active_subscription(
    user: User,
) -> tuple[Subscription | None, Plan | None]:
    async def _load(db):
        active_sub = await db.subscriptions.active_for_user(user.id)
        if active_sub is None:
            return None, None
        active_plan = await db.plans.get(active_sub.plan_id)
        return active_sub, active_plan

    return await db_call(_load)


async def _get_max_valid_until(user: User) -> datetime | None:
    return await db_call(lambda db: db.subscriptions.max_valid_until_for_user(user.id))


async def _get_pending_trial_subscription(
    user: User,
) -> tuple[Subscription | None, Plan | None]:
    async def _load(db):
        stmt = (
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "pending_payment",
                Plan.code == "trial",
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        res = await db._s.execute(stmt)
        row = res.first()
        if row is None:
            return None, None
        sub, plan = row
        return sub, plan

    return await db_call(_load)


async def _get_available_plans() -> list[Plan]:
    plans = await db_call(lambda db: db.plans.active())
    return [p for p in plans if p.code not in {"free", "trial"}]


async def build_main_view(
    tg_user_id: int,
    username: str | None,
    full_name: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await _get_user(tg_user_id, username, full_name)
    await _ensure_trial_subscription(user)
    active_sub, active_plan = await _get_active_subscription(user)
    if active_sub is None:
        pending_trial, pending_plan = await _get_pending_trial_subscription(user)
        if pending_trial is not None:
            active_sub = pending_trial
            active_plan = pending_plan
    if active_sub is None:
        plans = await _get_available_plans()
        text = (
            "Доступ приостановлен\n\n"
            "Верните доступ за минуту — выберите тариф"
        )
        rows = [
            [InlineKeyboardButton(f"{p.title} — {p.price_rub} ₽", callback_data=f"plan:{p.code}")]
            for p in plans
        ]
        if tg_user_id in settings.ADMIN_TG_ID:
            rows.append([InlineKeyboardButton("📣 Сделать рассылку", callback_data="admin_broadcast")])
        rows.append([InlineKeyboardButton("💬 Если у вас остались вопросы", callback_data="faq_main_menu")])
        rows.append([InlineKeyboardButton("🔁 Обновить", callback_data="refresh_main_menu")])
        return text, InlineKeyboardMarkup(rows)

    plan_title = active_plan.title if active_plan is not None else "неизвестен"
    max_valid_until = await _get_max_valid_until(user)
    days_left = _days_left(max_valid_until or active_sub.valid_until)
    connect_ref = _make_connect_ref(user.subscription_token)
    text = (
        "VPN готов к работе\n\n"
        "Доступно до 5 устройств\n\n"
        f"Тариф: {plan_title}\n"
        f"Осталось: {days_left}"
    )
    rows = [
        [InlineKeyboardButton("✨ Подключить", url=connect_ref)],
        [InlineKeyboardButton("🤝 Подключить другое устройство", callback_data="connect_other_device")],
    ]
    if tg_user_id in settings.ADMIN_TG_ID:
        rows.append([InlineKeyboardButton("📣 Сделать рассылку", callback_data="admin_broadcast")])
    rows.append([InlineKeyboardButton("💬 Если у вас остались вопросы", callback_data="faq_main_menu")])
    rows.append([InlineKeyboardButton("🔁 Обновить", callback_data="refresh_main_menu")])
    return text, InlineKeyboardMarkup(rows)


async def build_other_device_view(
    tg_user_id: int,
    username: str | None,
    full_name: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await _get_user(tg_user_id, username, full_name)
    await _ensure_trial_subscription(user)
    connect_ref = _make_connect_ref(user.subscription_token)
    share_ref = _make_share_ref(connect_ref)
    text = connect_ref
    rows = [
        [InlineKeyboardButton("📎 Скопировать", callback_data="copy_connect_link")],
        [InlineKeyboardButton("🌐 Открыть", url=connect_ref)],
        [InlineKeyboardButton("✉️ Переслать", url=share_ref)],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
    ]
    return text, InlineKeyboardMarkup(rows)


async def render_other_device(
    query: CallbackQuery,
    tg_user_id: int,
    username: str | None,
    full_name: str | None = None,
) -> None:
    text, reply_markup = await build_other_device_view(tg_user_id, username, full_name)
    await helpers.safe_edit(
        query,
        text=text,
        reply_markup=reply_markup,
        parse_mode=HTML,
        disable_web_page_preview=True,
    )


async def build_faq_view() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "Если у вас остались вопросы\n\n"
        "VPN работает автоматически\n"
        "Ничего настраивать не нужно\n\n"
        "Если что-то не произошло сразу — просто нажмите ещё раз\n"
        "Иногда система может спросить подтверждение — это нормально\n\n"
        "Одна и та же ссылка работает на нескольких устройствах\n"
        "Иногда требуется немного времени"
    )
    rows = [
        [InlineKeyboardButton("💬 Сообщить о проблеме", callback_data="fb_user_reply")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
    ]
    return text, InlineKeyboardMarkup(rows)


async def render_faq(
    query: CallbackQuery,
    tg_user_id: int,
    username: str | None,
) -> None:
    text, reply_markup = await build_faq_view()
    await helpers.safe_edit(
        query,
        text=text,
        reply_markup=reply_markup,
        parse_mode=HTML,
        disable_web_page_preview=True,
    )
