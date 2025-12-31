from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Response

from common.models import User
from common.db import db_call
from common.logger import Logger, Level
from common.xui_client.registry import Manager

app = FastAPI(title="Subscription service")

serverManager = Manager()
Logger.configure("subscription_service", level=Level.DEBUG)


def plainText(body: str, *, statusCode: int = 200) -> Response:
    return Response(
        content=body,
        status_code=statusCode,
        media_type="text/plain; charset=utf-8",
    )


@app.get("/sub/{token}")
async def getSubscription(token: str) -> Response:
    try:
        user: Optional[User] = await db_call(lambda db: db.users.byToken(token=token))
        if user is None:
            error = f"request \"/sub/{token}\": user not found"
            Logger.debug(error)
            return plainText(error, statusCode=404)

        name = user.username or str(user.tg_user_id)
        Logger.debug('request "/sub/%s": user="%s"', token, name)

        configs = await serverManager.collectConfigs(str(user.id))
        Logger.debug('user "%s" got %d configs', name, len(configs))

        body = "\n".join(configs) + ("\n" if configs else "")
        return plainText(body)

    except Exception as e:
        # лучше логировать stacktrace
        error = f"An error occurred while processing the request \"/sub/{token}\"\nError: \"{e}\""
        Logger.exception(error)
        return plainText(error, statusCode=500)
