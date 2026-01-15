from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import os

from typing import Optional

from fastapi import FastAPI, Response, Request
from urllib.parse import quote

from common.models import User
from common.db import db_call, init_db_engine
from common.logger import Logger, Level
from common.xui_client.registry import Manager
from subscription_service.stats import daily_stats_task

from subscription_service.admin.router import admin_router
from fastapi.staticfiles import StaticFiles

init_db_engine(
    os.environ["VPN_SUBSCRIPTION_DB_USERNAME"],
    os.environ["VPN_SUBSCRIPTION_DB_PASSWORD"],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.serverManager = Manager()
    app.state.stats_task = asyncio.create_task(daily_stats_task(app.state.serverManager))
    yield
    task = app.state.stats_task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # при необходимости: app.state.serverManager.close() / cleanup

app = FastAPI(title="Subscription service", lifespan=lifespan)
app.include_router(admin_router, prefix="/admin")
app.mount("/admin/static", StaticFiles(directory="subscription_service/admin/static"), name="admin-static")

Logger.configure("subscription_service", level=Level.DEBUG)
Logger.silence("httpcore.http11", "httpcore.connection", "httpx", "python_multipart.multipart", level=Level.WARNING)

V2BOX_ANDROID_STORE_URL = (
    os.environ.get("V2BOX_ANDROID_STORE_URL")
    or "https://play.google.com/store/apps/details?id=dev.hexasoftware.v2box&hl=ru"
)
V2BOX_IOS_STORE_URL = (
    os.environ.get("V2BOX_IOS_STORE_URL")
    or "https://apps.apple.com/ru/app/v2box-v2ray-client/id6446814690"
)
V2BOX_DEEPLINK_TEMPLATE = (
    os.environ.get("V2BOX_DEEPLINK_TEMPLATE")
    or "v2box://install-sub?url={url}&name={name}"
)
V2BOX_SUBSCRIPTION_NAME = "Ches-VPN"


def plainText(body: str, *, statusCode: int = 200) -> Response:
    return Response(
        content=body,
        status_code=statusCode,
        media_type="text/plain; charset=utf-8",
    )

def _detect_platform(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "android" in ua:
        return "android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "ios"
    return "other"

def _connect_page_html(
    *,
    platform: str,
    deeplink_url: str,
    store_url: str,
    sub_url: str,
    store_links_html: str,
) -> str:
    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Подключение V2Box</title>
    <style>
      :root {{
        --ink: #0f1b2d;
        --muted: #5a6b7f;
        --brand: #0b5fff;
        --brand-2: #00bfa6;
        --surface: #ffffff;
        --surface-2: #f2f6ff;
        --stroke: #e2e8f5;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Space Grotesk", "SF Pro Display", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(1200px 600px at 10% -10%, #e8f0ff 0%, transparent 60%),
          radial-gradient(900px 400px at 90% 0%, #e8fff7 0%, transparent 55%),
          #f7f9fc;
      }}
      .wrap {{
        max-width: 980px;
        margin: 0 auto;
        padding: 32px 20px 56px;
      }}
      .hero {{
        background: var(--surface);
        border: 1px solid var(--stroke);
        border-radius: 20px;
        padding: 28px;
        box-shadow: 0 12px 32px rgba(15, 27, 45, 0.08);
        display: grid;
        gap: 18px;
      }}
      .kicker {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        border-radius: 999px;
        background: var(--surface-2);
        color: var(--muted);
        font-size: 13px;
        letter-spacing: 0.2px;
      }}
      h1 {{
        font-size: 30px;
        line-height: 1.1;
        margin: 0;
      }}
      .lead {{
        margin: 0;
        color: var(--muted);
        font-size: 16px;
      }}
      .actions {{
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
      }}
      .btn {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 12px 18px;
        background: var(--brand);
        color: #fff;
        text-decoration: none;
        border-radius: 12px;
        font-weight: 600;
        box-shadow: 0 10px 24px rgba(11, 95, 255, 0.24);
      }}
      .btn.secondary {{
        background: #fff;
        color: var(--ink);
        border: 1px solid var(--stroke);
        box-shadow: none;
      }}
      .grid {{
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--stroke);
        border-radius: 16px;
        padding: 16px;
      }}
      .card h3 {{
        margin: 0 0 8px;
        font-size: 15px;
      }}
      .muted {{ color: var(--muted); font-size: 14px; }}
      .code {{
        padding: 12px;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 12px;
        font-family: "SF Mono", "Consolas", monospace;
        font-size: 12px;
        word-break: break-all;
      }}
      .share {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        align-items: center;
      }}
      .pulse {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: var(--brand-2);
        box-shadow: 0 0 0 6px rgba(0, 191, 166, 0.2);
      }}
      .footer {{
        margin-top: 18px;
        font-size: 13px;
        color: var(--muted);
      }}
      @media (max-width: 560px) {{
        h1 {{ font-size: 24px; }}
        .hero {{ padding: 20px; }}
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <div class="kicker"><span class="pulse"></span>Подключение в один шаг</div>
        <h1>Откройте V2Box и подключите VPN</h1>
        <p class="lead">
          Мы попробуем открыть приложение и сразу импортировать вашу подписку.
          Если приложения нет, откроется магазин для установки.
        </p>
        <div class="actions">
          <a class="btn" href="{deeplink_url}">Открыть V2Box</a>
          <button class="btn secondary" type="button" id="copy-btn">Скопировать ссылку</button>
        </div>
        <div class="code" id="sub-url">{sub_url}</div>
        <div class="footer">
          {store_links_html}
        </div>
      </section>

      <div class="grid" style="margin-top: 18px;">
        <div class="card">
          <h3>Расскажите другу</h3>
          <p class="muted">Чем больше людей подключаются, тем быстрее мы добавляем новые серверы и улучшения.</p>
        </div>
        <div class="card">
          <h3>Простой онбординг</h3>
          <p class="muted">Если открытие приложения не сработало, вставьте ссылку в V2Box вручную.</p>
        </div>
        <div class="card">
          <h3>Поддержка</h3>
          <p class="muted">Если что-то пошло не так, вернитесь в бот и напишите в поддержку.</p>
        </div>
      </div>
    </div>
    <script>
      (function() {{
        var deeplink = {deeplink_url!r};
        var storeUrl = {store_url!r};
        if (deeplink) {{
          window.location = deeplink;
          if (storeUrl) {{
            setTimeout(function() {{ window.location = storeUrl; }}, 1500);
          }}
        }}
        var copyBtn = document.getElementById("copy-btn");
        var subUrlEl = document.getElementById("sub-url");
        if (copyBtn && subUrlEl && navigator.clipboard) {{
          copyBtn.addEventListener("click", function() {{
            navigator.clipboard.writeText(subUrlEl.textContent || "");
            copyBtn.textContent = "Скопировано";
            setTimeout(function() {{ copyBtn.textContent = "Скопировать ссылку"; }}, 1400);
          }});
        }}
      }})();
    </script>
  </body>
</html>"""


@app.get("/sub/{token}")
async def getSubscription(request: Request, token: str) -> Response:
    try:
        user: Optional[User] = await db_call(lambda db: db.users.byToken(token=token))
        if user is None:
            error = f"request \"/sub/{token}\": user not found"
            Logger.debug(error)
            return plainText(error, statusCode=404)

        name = user.username or str(user.tg_user_id)
        Logger.debug('request "/sub/%s": user="%s"', token, name)

        server_manager: Manager = request.app.state.serverManager
        configs = await server_manager.collect_configs(str(user.id))
        Logger.debug('user "%s" got %d configs', name, len(configs))

        body = "\n".join(configs) + ("\n" if configs else "")
        return plainText(body)

    except Exception as e:
        error = f"An error occurred while processing the request \"/sub/{token}\"\nError: \"{e}\""
        Logger.exception(error)
        return plainText(error, statusCode=500)

@app.get("/connect/{token}")
async def connect_subscription(request: Request, token: str) -> Response:
    try:
        user: Optional[User] = await db_call(lambda db: db.users.byToken(token=token))
        if user is None:
            error = f"request \"/connect/{token}\": user not found"
            Logger.debug(error)
            return plainText(error, statusCode=404)

        user_agent = request.headers.get("user-agent", "")
        platform = _detect_platform(user_agent)
        name = user.username or str(user.tg_user_id)
        Logger.debug('request "/connect/%s": user="%s" platform="%s"', token, name, platform)

        base_url = str(request.base_url).rstrip("/")
        sub_url = f"{base_url}/sub/{token}"
        name_encoded = quote(V2BOX_SUBSCRIPTION_NAME, safe="")
        deeplink_url = V2BOX_DEEPLINK_TEMPLATE.format(url=sub_url, name=name_encoded)

        if platform == "ios":
            store_url = V2BOX_IOS_STORE_URL
            store_links_html = (
                f'<p class="muted">App Store: {store_url}</p>'
            )
        elif platform == "android":
            store_url = V2BOX_ANDROID_STORE_URL
            store_links_html = (
                f'<p class="muted">Google Play: {store_url}</p>'
            )
        else:
            store_url = ""
            store_links_html = (
                f'<p class="muted">App Store: {V2BOX_IOS_STORE_URL}</p>'
                f'<p class="muted">Google Play: {V2BOX_ANDROID_STORE_URL}</p>'
            )

        html = _connect_page_html(
            platform=platform,
            deeplink_url=deeplink_url,
            store_url=store_url,
            sub_url=sub_url,
            store_links_html=store_links_html,
        )
        return Response(content=html, media_type="text/html; charset=utf-8")

    except Exception as e:
        error = f"An error occurred while processing the request \"/connect/{token}\"\nError: \"{e}\""
        Logger.exception(error)
        return plainText(error, statusCode=500)
