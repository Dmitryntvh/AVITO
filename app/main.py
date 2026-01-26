import os
import re
import hmac
import hashlib

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import (
    init_db,
    insert_lead,
    list_models,
    get_model,
    upsert_model,
    replace_kits,
    replace_images,
    delete_model,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "")


def get_admin_ids():
    ids = set()
    for part in ADMIN_TG_IDS_RAW.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = get_admin_ids()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

PHONE_RE = re.compile(r"\D+")


def normalize_phone(raw):
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
    pairs = [f"{k}={v}" for k, v in data.items() if k != "hash"]
    pairs.sort()
    data_check_string = "\n".join(pairs)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac_hash == check_hash


def parse_kits_text(kits_text):
    kits = []
    for line in (kits_text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        material, price = line.split("|", 1)
        material = material.strip()
        price = price.strip().replace(" ", "")
        if not material:
            continue
        try:
            price_int = int(price)
        except ValueError:
            continue
        kits.append({"material": material, "price": price_int})
    return kits


def kits_to_text(kits):
    return "\n".join([f"{k['material']} | {k['price']}" for k in kits or []])


def parse_images_text(images_text):
    urls = []
    for line in (images_text or "").splitlines():
        url = line.strip()
        if not url:
            continue
        # минимальная фильтрация
        if url.startswith("http://") or url.startswith("https://"):
            urls.append(url)
    # убираем дубликаты, сохраняя порядок
    seen = set()
    unique = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)
    return unique


def images_to_text(urls):
    return "\n".join(urls or [])


@app.on_event("startup")
def startup():
    init_db()


# ----------------------
# PUBLIC
# ----------------------
@app.get("/", response_class=HTMLResponse)
def root():
    models = list_models()
    if models:
        return RedirectResponse(f"/go/{models[0]['code']}?src=root", status_code=303)
    return RedirectResponse("/admin/models", status_code=303)


@app.get("/go/{model_code}", response_class=HTMLResponse)
def phone_gate(request: Request, model_code: str, src: str = "unknown"):
    return templates.TemplateResponse("phone_gate.html", {"request": request, "model_code": model_code, "src": src})


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

    lead_id = insert_lead(phone=phone_norm, source=src, model_code=model_code or None)

    resp = RedirectResponse(f"/models/{model_code}", status_code=303)
    resp.set_cookie("lead_id", lead_id, max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax")
    return resp


@app.get("/models/{model_code}", response_class=HTMLResponse)
def model_page(request: Request, model_code: str):
    model = get_model(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    view_model = {
        "name": model["name"],
        "short": model["short"],
        "prices": {"drawings": model["price_drawings"], "kits": model["kits"]},
        "images": model.get("images", []),
    }

    return templates.TemplateResponse("model.html", {"request": request, "model": view_model, "model_code": model_code})


@app.get("/drawings/{model_code}", response_class=HTMLResponse)
def drawings_page(request: Request, model_code: str):
    lead_id = request.cookies.get("lead_id")
    if not lead_id:
        return RedirectResponse(f"/go/{model_code}?src=drawings", status_code=303)

    model = get_model(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    if not model["drawings_url"]:
        return HTMLResponse("<h1>Ссылка на чертежи не задана</h1>", status_code=404)

    return templates.TemplateResponse(
        "drawings.html",
        {"request": request, "model": {"name": model["name"]}, "model_code": model_code, "drawings_url": model["drawings_url"]},
    )


# ----------------------
# ADMIN: TELEGRAM
# ----------------------
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request):
    if not TELEGRAM_BOT_USERNAME:
        return HTMLResponse("<h1>TELEGRAM_BOT_USERNAME not set</h1>", status_code=500)

    base = str(request.base_url).rstrip("/")
    auth_url = f"{base}/admin/auth/telegram"

    return templates.TemplateResponse("admin_login.html", {"request": request, "bot_username": TELEGRAM_BOT_USERNAME, "auth_url": auth_url})


@app.get("/admin/auth/telegram")
def admin_auth_telegram(request: Request):
    if not TELEGRAM_BOT_TOKEN:
        return HTMLResponse("<h1>TELEGRAM_BOT_TOKEN not set</h1>", status_code=500)

    data = dict(request.query_params)

    if not telegram_check_auth(data, TELEGRAM_BOT_TOKEN):
        return HTMLResponse("<h1>Telegram auth failed</h1>", status_code=403)

    user_id = int(data.get("id", "0"))
    if user_id not in ADMIN_IDS:
        return HTMLResponse("<h1>Access denied</h1>", status_code=403)

    request.session["is_admin"] = True
    request.session["tg_user_id"] = user_id
    request.session["tg_username"] = data.get("username", "")

    return RedirectResponse("/admin/models", status_code=303)


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ----------------------
# ADMIN: CATALOG
# ----------------------
@app.get("/admin/models", response_class=HTMLResponse)
def admin_models(request: Request):
    require_admin(request)
    models = list_models()
    return templates.TemplateResponse("admin_models.html", {"request": request, "models": models, "tg_username": request.session.get("tg_username")})


@app.get("/admin/models/new", response_class=HTMLResponse)
def admin_model_new(request: Request):
    require_admin(request)
    empty = {"code": "", "name": "", "short": "", "price_drawings": 0, "drawings_url": "", "kits_text": "", "images_text": ""}
    return templates.TemplateResponse("admin_model_form.html", {"request": request, "m": empty, "is_new": True})


@app.get("/admin/models/{code}", response_class=HTMLResponse)
def admin_model_edit(request: Request, code: str):
    require_admin(request)
    model = get_model(code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    m = {
        "code": model["code"],
        "name": model["name"],
        "short": model["short"],
        "price_drawings": model["price_drawings"],
        "drawings_url": model["drawings_url"],
        "kits_text": kits_to_text(model.get("kits", [])),
        "images_text": images_to_text(model.get("images", [])),
    }
    return templates.TemplateResponse("admin_model_form.html", {"request": request, "m": m, "is_new": False})


@app.post("/admin/models/save")
def admin_model_save(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    short: str = Form(""),
    price_drawings: str = Form("0"),
    drawings_url: str = Form(""),
    kits_text: str = Form(""),
    images_text: str = Form(""),
):
    require_admin(request)

    code = (code or "").strip()
    name = (name or "").strip()
    short = (short or "").strip()
    drawings_url = (drawings_url or "").strip()

    if not code or not name:
        return HTMLResponse("<h1>Нужно заполнить code и name</h1>", status_code=400)

    try:
        pd = int((price_drawings or "0").replace(" ", ""))
    except ValueError:
        pd = 0

    upsert_model(code=code, name=name, short=short, price_drawings=pd, drawings_url=drawings_url)

    kits = parse_kits_text(kits_text)
    replace_kits(model_code=code, kits=kits)

    urls = parse_images_text(images_text)
    replace_images(model_code=code, urls=urls)

    return RedirectResponse(f"/admin/models/{code}", status_code=303)


@app.post("/admin/models/delete")
def admin_model_delete(request: Request, code: str = Form(...)):
    require_admin(request)
    delete_model(code)
    return RedirectResponse("/admin/models", status_code=303)
