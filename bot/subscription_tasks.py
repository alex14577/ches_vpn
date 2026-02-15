from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from sqlalchemy import select, update as sa_update

from common.db import db_call
from common.logger import Logger
from common.models import Plan, Subscription, User


async def overdue_notification_task(app: Application) -> None:
    while True:
        try:
            async def work(db):
                stmt = (
                    select(Subscription, User)
                    .join(User, User.id == Subscription.user_id)
                    .where(
                        Subscription.status == "payment_overdue",
                        Subscription.notified_overdue.is_(False),
                    )
                    .order_by(Subscription.created_at.asc())
                    .limit(100)
                )
                res = await db._s.execute(stmt)
                return list(res.all())

            rows = await db_call(work)
            for sub, user in rows:
                try:
                    await app.bot.send_message(
                        chat_id=user.tg_user_id,
                        text=(
                            "Время на оплату истекло.\n\n"
                            "Нажмите «Продлить», чтобы начать оплату заново."
                        ),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("Продлить", callback_data="choose_plan")]]
                        ),
                    )
                except Exception:
                    Logger.exception("Failed to notify overdue subscription: sub_id=%s", sub.id)
                    continue

                async def mark_notified(db):
                    await db._s.execute(
                        sa_update(Subscription)
                        .where(Subscription.id == sub.id)
                        .values(notified_overdue=True)
                    )
                    await db._s.flush()

                await db_call(mark_notified)
        except Exception:
            Logger.exception("overdue_notification_task failed")

        await asyncio.sleep(30)


async def expiry_reminder_task(app: Application) -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            start = now + timedelta(days=3)
            end = start + timedelta(hours=1)

            async def work(db):
                stmt = (
                    select(Subscription, User, Plan)
                    .join(User, User.id == Subscription.user_id)
                    .join(Plan, Plan.id == Subscription.plan_id)
                    .where(
                        Subscription.status == "active",
                        Subscription.valid_until.isnot(None),
                        Subscription.valid_until >= start,
                        Subscription.valid_until < end,
                        Subscription.reminded_at.is_(None),
                    )
                    .order_by(Subscription.valid_until.asc())
                )
                res = await db._s.execute(stmt)
                return list(res.all())

            rows = await db_call(work)
            for sub, user, plan in rows:
                try:
                    await app.bot.send_message(
                        chat_id=user.tg_user_id,
                        text=(
                            f"Подписка «{plan.title}» скоро закончится.\n"
                            "До окончания осталось около 3 дней.\n\n"
                            "Продлить сейчас?"
                        ),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("Продлить", callback_data="choose_plan")]]
                        ),
                    )
                except Exception:
                    Logger.exception("Failed to send expiry reminder: sub_id=%s", sub.id)
                    continue

                async def mark_reminded(db):
                    await db._s.execute(
                        sa_update(Subscription)
                        .where(Subscription.id == sub.id)
                        .values(reminded_at=datetime.now(timezone.utc))
                    )
                    await db._s.flush()

                await db_call(mark_reminded)
        except Exception:
            Logger.exception("expiry_reminder_task failed")

        await asyncio.sleep(3600)


async def expired_notification_task(app: Application) -> None:
    while True:
        try:
            async def work(db):
                stmt = (
                    select(Subscription, User, Plan)
                    .join(User, User.id == Subscription.user_id)
                    .join(Plan, Plan.id == Subscription.plan_id)
                    .where(
                        Subscription.status == "expired",
                        Subscription.notified_expired.is_(False),
                    )
                    .order_by(Subscription.valid_until.desc().nullslast())
                    .limit(100)
                )
                res = await db._s.execute(stmt)
                return list(res.all())

            rows = await db_call(work)
            for sub, user, plan in rows:
                try:
                    await app.bot.send_message(
                        chat_id=user.tg_user_id,
                        text=(
                            f"Подписка «{plan.title}» закончилась.\n\n"
                            "Чтобы восстановить доступ, продлите подписку."
                        ),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("Продлить", callback_data="choose_plan")]]
                        ),
                    )
                except Exception:
                    Logger.exception("Failed to send expired notification: sub_id=%s", sub.id)
                    continue

                async def mark_notified(db):
                    await db._s.execute(
                        sa_update(Subscription)
                        .where(Subscription.id == sub.id)
                        .values(notified_expired=True)
                    )
                    await db._s.flush()

                await db_call(mark_notified)
        except Exception:
            Logger.exception("expired_notification_task failed")

        await asyncio.sleep(60)
