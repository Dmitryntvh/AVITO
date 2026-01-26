import os
import re
import hmac
import hashlib

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db, insert_lead
from .models_data import MODELS


# ======================
# CONFIG
# ======================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "")


def get_admin_ids() -> set[int]:
    ids = set()
    for part in ADMIN_TG_IDS_RAW.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = get_admin_ids()


# ======================
# APP INIT
# ======================

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=True,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ======================
# HELPERS
# ======================

PHONE_RE = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    s = PHONE_RE.sub("", raw or "")
    if len(s) == 11 and s.startswith("8"):
        s = "7" + s[1:]
    if len(s) == 10:
        s = "7" + s
    if len(s) != 11 or not s.startswith("7"):
        return ""
    return "+" + s


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Not authorized")


def telegram_check_auth(data: dict, bot_token: str) -> bool:
    if "hash" not in data:
        return False

    check_hash = data["hash"]

    pairs = []
    for k, v in data.items():
        if k != "hash":
            pairs.append(f"{k}={v}")

    pairs.sort()
    data_check_string = "\n".join(pairs)

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hmac_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac_hash == check_hash


# ======================
# STARTUP
# ======================

@app.on_event("startup")
def startup():
    init_db()


# ======================
# PUBLIC SITE
# ======================

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/go/polar-6?src=root", status_code=303)


@app.get("/go/{model_code}", response_class=HTMLResponse)
def phone_gate(request: Request, model_code: str, src: str = "unknown"):
    return templates.TemplateResponse(
        "phone_gate.html",
        {
            "request": request,
            "model_code": model_code,
            "src": src,
        },
    )


@app.post("/go/submit")
def submit_phone(
    phone: str = Form(...),
    agree: str = Form(None),
    model_code: str = Form(""),
    src: str = Form("unknown"),
):
    if agree is None:
        return RedirectResponse(f"/go/{model_code}?src={src}", status_code=303)

    phone_norm = normalize_phone(phone)
    if not phone_norm:
        return RedirectResponse(f"/go/{model_code}?src={src}", status_code=303)

    lead_id = insert_lead(
        phone=phone_norm,
        source=src,
        model_code=model_code or None,
    )

    resp = RedirectResponse(f"/models/{model_code}", status_code=303)
    resp.set_cookie(
        key="lead_id",
        value=lead_id,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.get("/models/{model_code}", response_class=HTMLResponse)
def model_page(request: Request, model_code: str):
    model = MODELS.get(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    return templates.TemplateResponse(
        "model.html",
        {
            "request": request,
            "model": model,
            "model_code": model_code,
        },
    )


@app.get("/drawings/{model_code}", response_class=HTMLResponse)
def drawings_page(request: Request, model_code: str):
    lead_id = request.cookies.get("lead_id")
    if not lead_id:
        return RedirectResponse(f"/go/{model_code}?src=drawings", status_code=303)

    model = MODELS.get(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    drawings_url = model.get("drawings_url")
    if not drawings_url:
        return HTMLResponse("<h1>Ссылка на чертежи не задана</h1>", status_code=404)

    return templates.TemplateResponse(
        "drawings.html",
        {
            "request": request,
            "model": model,
            "model_code": model_code,
            "drawings_url": drawings_url,
        },
    )


# ======================
# ADMIN — TELEGRAM LOGIN
# ======================

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request):
    if not TELEGRAM_BOT_USERNAME:
        return HTMLResponse("TELEGRAM_BOT_USERNAME not set", status_code=500)

    base = str(request.base_url).rstrip("/")
    auth_url = f"{base}/admin/auth/telegram"

    return templates.TemplateResponse(
        "admin_login.html",
        {
            "request": request,
            "bot_username": TELEGRAM_BOT_USERNAME,
            "auth_url": auth_url,
        },
    )


@app.get("/admin/auth/telegram")
def admin_auth_telegram(request: Request):
    if not TELEGRAM_BOT_TOKEN:
        return HTMLResponse("TELEGRAM_BOT_TOKEN not set", status_code=500)

    data = dict(request.query_params)

    if not telegram_check_auth(data, TELEGRAM_BOT_TOKEN):
        return HTMLResponse("Telegram auth failed", status_code=403)

    user_id = int(data.get("id", "0"))
    if user_id not in ADMIN_IDS:
        return HTMLResponse("Access denied", status_code=403)

    request.session["is_admin"] = True
    request.session["tg_user_id"] = user_id
    request.session["tg_username"] = data.get("username", "")

    return RedirectResponse("/admin", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        "admin_home.html",
        {
            "request": request,
            "tg_username": request.session.get("tg_username"),
        },
    )


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
