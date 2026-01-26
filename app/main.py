import re
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .db import init_db, insert_lead
from .models_data import MODELS

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

PHONE_RE = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """
    Нормализация телефона к формату +7XXXXXXXXXX
    Принимаем: 8XXXXXXXXXX, 9XXXXXXXXX, +7..., с пробелами и дефисами.
    """
    s = PHONE_RE.sub("", raw or "")
    if len(s) == 11 and s.startswith("8"):
        s = "7" + s[1:]
    if len(s) == 10:
        s = "7" + s
    if len(s) != 11 or not s.startswith("7"):
        return ""
    return "+" + s


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    # Главную позже сделаем красивую. Пока редирект на популярную модель.
    return RedirectResponse(url="/go/polar-6?src=root", status_code=303)


@app.get("/go/{model_code}", response_class=HTMLResponse)
def go_model(request: Request, model_code: str, src: str = "unknown"):
    # Если модель неизвестна — можно редиректнуть на общий каталог позже.
    return templates.TemplateResponse(
        "phone_gate.html",
        {"request": request, "model_code": model_code, "src": src},
    )


@app.post("/go/submit")
def go_submit(
    phone: str = Form(...),
    agree: str = Form(None),
    model_code: str = Form(""),
    src: str = Form("unknown"),
):
    # Без согласия не пускаем
    if agree is None:
        return RedirectResponse(url=f"/go/{model_code}?src={src}", status_code=303)

    phone_norm = normalize_phone(phone)
    if not phone_norm:
        return RedirectResponse(url=f"/go/{model_code}?src={src}", status_code=303)

    # Сохраняем лид в БД
    lead_id = insert_lead(phone=phone_norm, source=src, model_code=model_code or None)

    # Редирект на страницу модели + ставим cookie, чтобы открыть чертежи
    resp = RedirectResponse(url=f"/models/{model_code}", status_code=303)
    resp.set_cookie(
        key="lead_id",
        value=lead_id,
        max_age=60 * 60 * 24 * 30,  # 30 дней
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
        {"request": request, "model": model, "model_code": model_code},
    )


@app.get("/drawings/{model_code}", response_class=HTMLResponse)
def drawings_page(request: Request, model_code: str):
    # Доступ только после ввода телефона (проверяем cookie)
    lead_id = request.cookies.get("lead_id")
    if not lead_id:
        return RedirectResponse(url=f"/go/{model_code}?src=drawings", status_code=303)

    model = MODELS.get(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    drawings_url = model.get("drawings_url")
    if not drawings_url:
        return HTMLResponse("<h1>Ссылка на чертежи пока не добавлена</h1>", status_code=404)

    return templates.TemplateResponse(
        "drawings.html",
        {
            "request": request,
            "model": model,
            "model_code": model_code,
            "drawings_url": drawings_url,
        },
    )
