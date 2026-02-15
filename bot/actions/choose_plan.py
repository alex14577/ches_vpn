from datetime import datetime, timezone, timedelta
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, update as sa_update
from sqlalchemy.exc import IntegrityError

from bot.actions import return_main_menu, settings
from bot.helpers import helpers
from common.db import db_call
from common.models import Plan, Subscription

from telegram.constants import ParseMode

HTML = ParseMode.HTML


async def show_plans(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    plans = await db_call(lambda db: db.plans.active())
    plans = [p for p in plans if p.code != "free" and p.code != "trial"]

    if not plans:
        await helpers.safe_edit(
            query,
            text="Доступных подписок сейчас нет.",
            reply_markup=return_main_menu.keyboard(),
            parse_mode=HTML,
        )
        return

    rows = [
        [InlineKeyboardButton(f"{p.title} — {p.price_rub} ₽", callback_data=f"plan:{p.code}")]
        for p in plans
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])

    await helpers.safe_edit(
        query,
        text="Выберите подписку:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=HTML,
    )


async def _find_free_amount(db, base_minor: int) -> int | None:
    low = base_minor + 1
    high = base_minor + 99

    res = await db._s.execute(
        select(Subscription.expected_amount_minor).where(
            Subscription.status == "pending_payment",
            Subscription.expected_amount_minor.between(low, high),
        )
    )
    used = [row[0] for row in res.all()]
    used_set = {val for val in used if isinstance(val, int)}
    for cents in range(1, 100):
        candidate = base_minor + cents
        if candidate not in used_set:
            return candidate
    return None


def _format_amount(amount_minor: int) -> str:
    rub = amount_minor // 100
    kop = amount_minor % 100
    return f"{rub}.{kop:02d}"


async def show_plan_details(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    tg_user_id: int,
    username: str | None,
    plan_code: str,
) -> None:
    plan: Plan = await db_call(lambda db: db.plans.getByCode(plan_code))
    if plan is None or not plan.is_active:
        await helpers.safe_edit(
            query,
            text="Подписка не найдена.",
            reply_markup=return_main_menu.keyboard(),
            parse_mode=HTML,
        )
        return

    async def work(db):
        user = await db.users.getOrCreate(tg_user_id, username)
        active_sub = await db.subscriptions.active_for_user(user.id)

        if active_sub is not None and active_sub.valid_until is None:
            return "unlimited", None, plan

        res = await db._s.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "pending_payment",
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        existing = res.scalar_one_or_none()
        if existing is not None and existing.plan_id != plan.id:
            await db._s.execute(
                sa_update(Subscription)
                .where(Subscription.id == existing.id)
                .values(status="canceled", updated_at=datetime.now(timezone.utc))
            )
            await db._s.flush()
            existing = None

        if existing is not None:
            plan_for_sub = await db.plans.get(existing.plan_id)
            return "ok", existing, plan_for_sub

        base_minor = int(plan.price_rub) * 100
        max_valid_until = await db.subscriptions.max_valid_until_for_user(user.id)
        now = datetime.now(timezone.utc)
        start = max(now, max_valid_until) if max_valid_until is not None else now

        valid_until = None
        if plan.duration_days is not None:
            valid_until = start + timedelta(days=int(plan.duration_days))

        for _ in range(5):
            amount_minor = await _find_free_amount(db, base_minor)
            if amount_minor is None:
                amount_minor = await _find_free_amount(db, base_minor + 100)
            if amount_minor is None:
                return "no_amount", None, plan
            try:
                async with db._s.begin_nested():
                    sub = await db.subscriptions.add(
                        user_id=user.id,
                        plan_id=plan.id,
                        valid_from=start,
                        valid_until=valid_until,
                        expected_amount_minor=amount_minor,
                        status="pending_payment",
                    )
                return "ok", sub, plan
            except IntegrityError:
                continue

        return "no_amount", None, plan

    result, sub, plan_for_sub = await db_call(work)
    plan_for_sub = plan_for_sub or plan

    if result == "unlimited":
        await helpers.safe_edit(
            query,
            text="У вас уже бессрочная активная подписка. Продление не требуется.",
            reply_markup=return_main_menu.keyboard(),
            parse_mode=HTML,
        )
        return

    if sub is None:
        await helpers.safe_edit(
            query,
            text="Сейчас нет свободных сумм для оплаты. Попробуйте позже.",
            reply_markup=return_main_menu.keyboard(),
            parse_mode=HTML,
        )
        return

    amount_str = _format_amount(sub.expected_amount_minor)
    text = (
        f"<b>{plan_for_sub.title}</b>\n\n"
        f"Сумма к оплате: <b>{amount_str} ₽</b>\n"
        f"Переведите по СБП на номер: <b>{settings.SBP_PHONE} ровно эту сумму</b> на <b>Альфа банк</b>\n\n"
        "После оплаты нажмите кнопку ниже."
    )
    await helpers.safe_edit(
        query,
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я оплатил(а)", callback_data=f"payment_sent:{sub.id}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="choose_plan")],
        ]),
        parse_mode=HTML,
    )


async def notify_payment_sent(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    subscription_id: str,
) -> None:
    try:
        sub_id = uuid.UUID(subscription_id)
    except ValueError:
        sub_id = None

    async def load(db):
        if sub_id is None:
            return None, None
        current_user = await db.users.byTgId(query.from_user.id)
        if current_user is None:
            return None, None
        res = await db._s.execute(
            select(Subscription, Plan).join(Plan, Plan.id == Subscription.plan_id).where(
                Subscription.id == sub_id
            )
        )
        row = res.first()
        return row, current_user

    row, current_user = await db_call(load)
    plan = row[1] if row else None
    sub = row[0] if row else None

    if sub is None or current_user is None or sub.user_id != current_user.id:
        await helpers.safe_edit(
            query,
            text="Подписка не найдена.",
            reply_markup=return_main_menu.keyboard(),
            parse_mode=HTML,
        )
        return

    user = query.from_user
    username = f"@{user.username}" if user and user.username else "без username"
    amount = _format_amount(sub.expected_amount_minor) if sub and sub.expected_amount_minor else "неизвестно"
    plan_title = plan.title if plan else "неизвестный план"

    text = (
        "Пользователь нажал «Я оплатил(а)»:\n"
        f"tg_id: {user.id if user else 'unknown'}\n"
        f"user: {username}\n"
        f"plan: {plan_title}\n"
        f"amount: {amount} ₽\n"
        f"subscription_id: {subscription_id}"
    )
    for admin_id in settings.ADMIN_TG_ID:
        await context.bot.send_message(chat_id=admin_id, text=text)

    await helpers.safe_edit(
        query,
        text="Спасибо! Мы уведомили администратора. Если оплата прошла, подписка активируется автоматически.",
        reply_markup=return_main_menu.keyboard(),
        parse_mode=HTML,
    )
