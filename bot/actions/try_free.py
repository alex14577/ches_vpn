from datetime import datetime, timezone
import os

from bot.utils import idem_key
from common.db import db_call
from common.models import Plan, Subscription, User, Task
from common.logger import Logger

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip()

# бесплатный тариф
async def try_free(tg_user_id, username):
    user: User = await db_call(lambda db: db.users.getOrCreate(tg_user_id, username))
    
    plan: Plan = await db_call(lambda db: db.plans.getByCode("free"))
    
    sub: Subscription = await db_call(lambda db: db.subscriptions.get(userId=user.id,
                                                                      planId=plan.id))
    
    if sub is None:
        sub: Subscription = await db_call(lambda db: db.subscriptions.add(userId=user.id,
                                                                          planId=plan.id,
                                                                          validFrom=datetime.now(timezone.utc),
                                                                          validUntil=None))
        task: Task = await db_call(lambda db: db.tasks.create_task(type_="add",
                                                                   payload={"user_tg_id": user.tg_user_id},
                                                                   idempotency_key=idem_key("get", tg_user_id)))
    
        Logger.debug("created task %s | type=%s | userTgId=%s | username=%s",
                     task.id,
                     task.type,
                     user.tg_user_id,
                     user.username or "None")
    
    return f"{PUBLIC_BASE_URL}/sub/{user.subscription_token}"
