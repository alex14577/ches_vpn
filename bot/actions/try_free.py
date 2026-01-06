from datetime import datetime, timezone

from common.db import db_call
from common.models import Plan, Subscription, User
from common.logger import Logger
from common.xui_client.registry import Manager
from bot.actions.settings import PUBLIC_BASE_URL

# бесплатный тариф
async def try_free(tg_user_id, username, serversManager: Manager):
    user: User = await db_call(lambda db: db.users.getOrCreate(tg_user_id, username))
    
    plan: Plan = await db_call(lambda db: db.plans.getByCode("free"))
    
    sub: Subscription = await db_call(lambda db: db.subscriptions.get(userId=user.id,
                                                                      planId=plan.id))
    
    if sub is None:
        sub: Subscription = await db_call(lambda db: db.subscriptions.add(user_id=user.id,
                                                                          plan_id=plan.id,
                                                                          valid_from=datetime.now(timezone.utc),
                                                                          valid_until=None))
        
    try:
        await serversManager.sync_user(user)
    except Exception as e:
        Logger.error("Failed to sync user in \"try_free\". Error %s", str(e))

    name = user.username or user.tg_user_id
    Logger.info("User \"%s\" added and synced for free plan", name)
    
    return f"{PUBLIC_BASE_URL}/sub/{user.subscription_token}"
