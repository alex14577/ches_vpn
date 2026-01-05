from __future__ import annotations
from contextlib import asynccontextmanager

from typing import Optional

from fastapi import FastAPI, Response

from common.models import User
from common.db import db_call
from common.logger import Logger, Level
from common.xui_client.registry import Manager

from subscription_service.admin.router import admin_router
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.serverManager = Manager()
    yield
    # при необходимости: app.state.serverManager.close() / cleanup

app = FastAPI(title="Subscription service", lifespan=lifespan)
app.include_router(admin_router, prefix="/admin")
app.mount("/admin/static", StaticFiles(directory="subscription_service/admin/static"), name="admin-static")

serverManager = Manager()
Logger.configure("subscription_service", level=Level.DEBUG)
Logger.silence("httpcore.http11", "httpcore.connection", "httpx", "python_multipart.multipart", level=Level.WARNING)


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

        configs = await serverManager.collect_configs(str(user.id))
        Logger.debug('user "%s" got %d configs', name, len(configs))

        body = "\n".join(configs) + ("\n" if configs else "")
        return plainText(body)

    except Exception as e:
        # лучше логировать stacktrace
        error = f"An error occurred while processing the request \"/sub/{token}\"\nError: \"{e}\""
        Logger.exception(error)
        return plainText(error, statusCode=500)
