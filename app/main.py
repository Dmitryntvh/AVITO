import re
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .db import init_db, insert_lead
from .models_data import MODELS

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

PHONE_RE = re.compile(r"\D+")

def normalize_phone(raw: str) -> str:
    s = PHONE_RE.sub("", raw or "")
    if len(s) == 11 and s.startswith("8"):
        s = "7" + s[1:]
    if len(s) == 10:
        s = "7" + s
    # на выходе: +7XXXXXXXXXX
    return "+" + s if s else ""

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/go/{model_code}", response_class=HTMLResponse)
def go_model(request: Request, model_code: str, src: str = "unknown"):
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
    if agree is None:
        return RedirectResponse(url=f"/go/{model_code}?src={src}", status_code=303)

    p = normalize_phone(phone)
    if not p or len(p) < 12:
        return RedirectResponse(url=f"/go/{model_code}?src={src}", status_code=303)

    insert_lead(phone=p, source=src, model_code=model_code or None)

    return RedirectResponse(url=f"/models/{model_code}", status_code=303)

@app.get("/models/{model_code}", response_class=HTMLResponse)
def model_page(request: Request, model_code: str):
    model = MODELS.get(model_code)
    if not model:
        return HTMLResponse("<h1>Модель не найдена</h1>", status_code=404)

    return templates.TemplateResponse(
        "model.html",
        {"request": request, "model": model, "model_code": model_code},
    )
