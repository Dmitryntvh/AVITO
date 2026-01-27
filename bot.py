import os
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ======================================================================
# Базовая конфигурация и импорт данных моделей
#
# В эту реализацию добавлена поддержка каталога моделей. Данные о моделях
# берутся из модуля `app.models_data`. Если модуль недоступен (например,
# отсутствует в локальной среде), переменная MODELS будет пустым
# словарём, чтобы бот не падал при отсутствии каталога.
# ======================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

# Попытка импортировать данные каталога. Если импорт не удался,
# MODELS остаётся пустым словарём.
try:
    from app.models_data import MODELS
except Exception:
    MODELS = {}

# =========================
# ENV
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

ADMIN_IDS = set()
for p in (ADMIN_TG_IDS_RAW or "").split(","):
    p = p.strip()
    if p.isdigit():
        ADMIN_IDS.add(int(p))


def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(u and u.id in ADMIN_IDS)


# =========================
# DB wrappers
# =========================
def db_init():
    from app.db import init_db
    init_db()


def db_count_leads():
    from app.db import count_leads
    return count_leads()


def db_list_leads(limit: int, offset: int):
    from app.db import list_leads
    return list_leads(limit=limit, offset=offset)


def db_get_lead(lead_id: str):
    from app.db import get_lead
    return get_lead(lead_id)


def db_set_status(lead_id: str, status: str):
    from app.db import set_lead_status
    return set_lead_status(lead_id, status)


def db_set_segment(lead_id: str, segment: str):
    from app.db import set_lead_segment
    return set_lead_segment(lead_id, segment)


def db_update_profile(lead_id: str, full_name=None, city=None, interest=None):
    from app.db import update_lead_profile
    return update_lead_profile(lead_id, full_name=full_name, city=city, interest=interest)


def db_append_note(lead_id: str, note_text: str):
    from app.db import append_lead_note
    return append_lead_note(lead_id, note_text)


def db_set_remind_at(lead_id: str, iso_or_none):
    from app.db import set_lead_remind_at
    return set_lead_remind_at(lead_id, iso_or_none)


def db_due_reminders(limit: int = 30):
    from app.db import due_reminders
    return due_reminders(limit=limit)


# =========================
# UI options
# =========================
# Переписанные статусы: минимальный набор для покупателей.
# waiting    – заказ ожидает подтверждения или завершения;
# contact_needed – требуется связаться с покупателем;
# completed  – заказ завершён и оплачен.
STATUS_OPTIONS = [
    ("waiting", "⌛ В ожидании заказа"),
    ("contact_needed", "📞 Требуется связаться"),
    ("completed", "✅ Завершён / оплачен"),
]

SEGMENT_OPTIONS = [
    ("private", "👤 Частник"),
    ("welder", "🧑‍🏭 Сварщик"),
    ("factory", "🏭 Производственник"),
]

INTEREST_OPTIONS = [
    ("drawings", "📐 Чертежи"),
    ("blanks", "🧱 Заготовка"),
    ("tub", "🛁 Готовый чан"),
    ("consult", "🧠 Консультация"),
    ("other", "🧩 Другое"),
]


def main_keyboard() -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру главного меню.

    По умолчанию содержит три основные кнопки:
    • 🛒 Покупатели — переход к списку покупателей
    • 🔔 Напоминания — просмотр просроченных напоминаний
    • 📦 Каталог — просмотр каталога моделей
    """
    return ReplyKeyboardMarkup(
        [["🛒 Покупатели", "🔔 Напоминания", "📦 Каталог"]],
        resize_keyboard=True,
    )


def fmt_dt(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    return str(v) if v else "—"


def lead_card_text(lead: dict) -> str:
    return (
        f"👤 Покупатель\n\n"
        f"ID: {lead['id']}\n"
        f"📞 Телефон: {lead.get('phone','—')}\n"
        f"👤 ФИО: {lead.get('full_name') or '—'}\n"
        f"🏙 Город: {lead.get('city') or '—'}\n"
        f"🎯 Интерес: {lead.get('interest') or '—'}\n\n"
        f"Источник: {lead.get('source','—')}\n"
        f"Модель: {lead.get('model_code') or '—'}\n"
        f"Сегмент: {lead.get('segment','unknown')}\n"
        f"Статус: {lead.get('status','waiting')}\n\n"
        f"Создан: {fmt_dt(lead.get('created_at'))}\n"
        f"Последний контакт: {fmt_dt(lead.get('last_contact_at'))}\n"
        f"Напоминание: {fmt_dt(lead.get('remind_at'))}\n\n"
        f"📝 Заметки:\n{lead.get('note') or '—'}"
    )


def lead_card_kb(lead_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧾 Анкета (по шагам)", callback_data=f"lead_form:{lead_id}")],
            [
                InlineKeyboardButton("🔁 Статус", callback_data=f"lead_status:{lead_id}"),
                InlineKeyboardButton("🏷 Сегмент", callback_data=f"lead_segment:{lead_id}"),
            ],
            [
                InlineKeyboardButton("📝 Заметка", callback_data=f"lead_note:{lead_id}"),
                InlineKeyboardButton("⏰ Напомнить", callback_data=f"lead_remind:{lead_id}"),
            ],
            [InlineKeyboardButton("⬅️ К списку", callback_data="leads_back")],
        ]
    )


def leads_list_kb(rows, offset: int, limit: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    for r in rows:
        lead_id = str(r["id"])
        phone = r.get("phone", "-")
        model = r.get("model_code") or "-"
        status = r.get("status", "waiting")
        buttons.append([InlineKeyboardButton(f"{phone} • {model} • {status}", callback_data=f"lead:{lead_id}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"leads:{max(offset - limit, 0)}:{limit}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"leads:{offset + limit}:{limit}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def status_kb(lead_id: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(lbl, callback_data=f"set_status:{lead_id}:{code}")]
            for code, lbl in STATUS_OPTIONS]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"lead:{lead_id}")])
    return InlineKeyboardMarkup(rows)


def segment_kb(lead_id: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(lbl, callback_data=f"set_segment:{lead_id}:{code}")]
            for code, lbl in SEGMENT_OPTIONS]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"lead:{lead_id}")])
    return InlineKeyboardMarkup(rows)


def remind_kb(lead_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏱ +2 часа", callback_data=f"set_remind:{lead_id}:2h"),
                InlineKeyboardButton("📅 Завтра 11:00", callback_data=f"set_remind:{lead_id}:tom11"),
            ],
            [
                InlineKeyboardButton("📆 +3 дня", callback_data=f"set_remind:{lead_id}:3d"),
                InlineKeyboardButton("🧹 Убрать", callback_data=f"set_remind:{lead_id}:clear"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"lead:{lead_id}")],
        ]
    )


# =========================
# Анкета: состояние и галочки
# =========================
FORM_STATE = {}          # user_id -> {"lead_id": str, "step": str}
INTEREST_TMP = {}        # (user_id, lead_id) -> set(codes)


def form_set(user_id: int, lead_id: str, step: str):
    FORM_STATE[user_id] = {"lead_id": lead_id, "step": step}


def form_get(user_id: int):
    return FORM_STATE.get(user_id)


def form_clear(user_id: int):
    FORM_STATE.pop(user_id, None)


def form_nav_kb(lead_id: str, back_step, allow_skip: bool = True):
    row = []
    if back_step:
        row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"form_back:{lead_id}:{back_step}"))
    if allow_skip:
        row.append(InlineKeyboardButton("⏭ Пропустить", callback_data=f"form_skip:{lead_id}"))

    return InlineKeyboardMarkup([
        row if row else [InlineKeyboardButton("⬅️ В карточку", callback_data=f"lead:{lead_id}")],
        [InlineKeyboardButton("✖️ Отмена", callback_data=f"lead:{lead_id}")],
    ])


def step_segment_kb(lead_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Частник", callback_data=f"form_set_segment:{lead_id}:private")],
        [InlineKeyboardButton("🧑‍🏭 Сварщик", callback_data=f"form_set_segment:{lead_id}:welder")],
        [InlineKeyboardButton("🏭 Производственник", callback_data=f"form_set_segment:{lead_id}:factory")],
        [InlineKeyboardButton("⬅️ Назад в карточку", callback_data=f"lead:{lead_id}")],
    ])


def step_status_kb(lead_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⌛ В ожидании заказа", callback_data=f"form_set_status:{lead_id}:waiting")],
        [InlineKeyboardButton("📞 Требуется связаться", callback_data=f"form_set_status:{lead_id}:contact_needed")],
        [InlineKeyboardButton("✅ Завершён / оплачен", callback_data=f"form_set_status:{lead_id}:completed")],
        [InlineKeyboardButton("⬅️ Назад в карточку", callback_data=f"lead:{lead_id}")],
    ])


def interest_codes_to_text(selected_set) -> str:
    mapping = {
        "drawings": "чертежи",
        "blanks": "заготовка",
        "tub": "готовый чан",
        "consult": "консультация",
        "other": "другое",
    }
    order = [code for code, _ in INTEREST_OPTIONS]
    return ", ".join(mapping[c] for c in order if c in selected_set)


def interest_kb(user_id: int, lead_id: str):
    selected = INTEREST_TMP.get((user_id, lead_id), set())
    rows = []
    for code, label in INTEREST_OPTIONS:
        mark = "✅ " if code in selected else "☐ "
        rows.append([InlineKeyboardButton(mark + label, callback_data=f"form_interest_toggle:{lead_id}:{code}")])

    rows.append([
        InlineKeyboardButton("✅ Готово", callback_data=f"form_interest_done:{lead_id}"),
        InlineKeyboardButton("🧹 Очистить", callback_data=f"form_interest_clear:{lead_id}"),
    ])
    rows.append([InlineKeyboardButton("⬅️ Назад в карточку", callback_data=f"lead:{lead_id}")])
    return InlineKeyboardMarkup(rows)


# ======================================================================
# Функции для отображения каталога моделей
# ======================================================================
def catalog_list_kb() -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру для списка моделей.
    Каждая кнопка содержит название модели и callback_data вида `model:code`.
    """
    rows = []
    for code, model in MODELS.items():
        name = model.get("name") or code
        rows.append([InlineKeyboardButton(name, callback_data=f"model:{code}")])
    return InlineKeyboardMarkup(rows)


def model_card_kb(model_code: str) -> InlineKeyboardMarkup:
    """
    Клавиатура карточки модели. Содержит кнопку для перехода к чертежам и
    кнопку возврата в каталог. Ссылка для чертежей берётся из модели.
    """
    rows = []
    model = MODELS.get(model_code, {})
    url = model.get("drawings_url")
    if url:
        rows.append([InlineKeyboardButton("📐 Чертежи", url=url)])
    rows.append([InlineKeyboardButton("⬅️ В каталог", callback_data="catalog_back")])
    return InlineKeyboardMarkup(rows)


async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отображает список всех доступных моделей.
    При нажатии на модель открывается её карточка.
    """
    text = "📦 Каталог моделей\nВыбери модель:"
    kb = catalog_list_kb()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def show_model(update: Update, context: ContextTypes.DEFAULT_TYPE, model_code: str):
    """
    Показывает подробную информацию о выбранной модели.
    Информация включает название, краткое описание, цены на чертежи и комплекты,
    а также ссылку на чертежи. Под карточкой выводится клавиатура для
    возврата в каталог и перехода к чертежам.
    """
    model = MODELS.get(model_code)
    if not model:
        msg = "Модель не найдена."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    text_lines = []
    text_lines.append(f"📦 {model.get('name','')}")
    short = model.get("short") or ""
    if short:
        text_lines.append("")
        text_lines.append(short)
    prices = model.get("prices") or {}
    drawings_price = prices.get("drawings")
    kits = prices.get("kits") or []
    if drawings_price:
        text_lines.append("")
        text_lines.append(f"💵 Цена чертежей: {drawings_price}₽")
    if kits:
        text_lines.append("")
        text_lines.append("⚙️ Комплекты:")
        for kit in kits:
            material = kit.get("material")
            price = kit.get("price")
            text_lines.append(f"• {material} — {price}₽")
    drawings_url = model.get("drawings_url")
    if drawings_url:
        text_lines.append("")
        text_lines.append(f"🔗 Ссылка на чертежи: {drawings_url}")
    text = "\n".join(text_lines)
    kb = model_card_kb(model_code)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def show_form_step(update: Update, context: ContextTypes.DEFAULT_TYPE, lead_id: str, step: str):
    user_id = update.effective_user.id
    form_set(user_id, lead_id, step)

    if step == "full_name":
        text = "1/6 👤 Введи ФИО одним сообщением.\nПример: Иванов Иван Иванович"
        kb = form_nav_kb(lead_id, back_step=None, allow_skip=True)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)
        return

    if step == "city":
        text = "2/6 🏙 Введи город.\nПример: Нижний Тагил"
        kb = form_nav_kb(lead_id, back_step="full_name", allow_skip=True)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)
        return

    if step == "segment":
        text = "3/6 🏷 Выбери тип клиента:"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=step_segment_kb(lead_id))
        else:
            await update.message.reply_text(text, reply_markup=step_segment_kb(lead_id))
        return

    if step == "interest":
        text = "4/6 🎯 Выбери интерес (можно несколько):"

        # предзаполнение из БД (простое)
        lead = db_get_lead(lead_id)
        current = (lead.get("interest") or "").lower()
        selected = set()
        if "черт" in current:
            selected.add("drawings")
        if "заготов" in current:
            selected.add("blanks")
        if "готов" in current or "чан" in current:
            selected.add("tub")
        if "конс" in current:
            selected.add("consult")
        if "дру" in current:
            selected.add("other")

        INTEREST_TMP[(user_id, lead_id)] = selected

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=interest_kb(user_id, lead_id))
        else:
            await update.message.reply_text(text, reply_markup=interest_kb(user_id, lead_id))
        return

    if step == "status":
        text = "5/6 🔁 Выбери статус:"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=step_status_kb(lead_id))
        else:
            await update.message.reply_text(text, reply_markup=step_status_kb(lead_id))
        return

    if step == "note":
        text = "6/6 📝 Напиши заметку (1 строка) или нажми «Пропустить»."
        kb = form_nav_kb(lead_id, back_step="status", allow_skip=True)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)
        return

    if step == "done":
        form_clear(user_id)
        await show_lead_card(update, context, lead_id)
        return


# =========================
# Views
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    if not ADMIN_IDS:
        await update.message.reply_text("⚠️ ADMIN_TG_IDS не задан. Добавь в Variables.")
        return
    await update.message.reply_text("CRM-бот ✅", reply_markup=main_keyboard())


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, limit: int = 20):
    total = db_count_leads()
    rows = db_list_leads(limit=limit, offset=offset)
    text = f"🛒 Покупатели {offset + 1}–{min(offset + limit, total)} из {total}\nВыбери покупателя:"
    kb = leads_list_kb(rows, offset, limit, total)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def show_lead_card(update: Update, context: ContextTypes.DEFAULT_TYPE, lead_id: str):
    lead = db_get_lead(lead_id)
    if not lead:
        msg = "Покупатель не найден."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    text = lead_card_text(lead)
    kb = lead_card_kb(lead_id)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


# =========================
# Handlers
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    user_id = update.effective_user.id
    txt = (update.message.text or "").strip()

    # анкета: текстовые шаги
    st = form_get(user_id)
    if st:
        lead_id = st["lead_id"]
        step = st["step"]

        if step == "full_name":
            db_update_profile(lead_id, full_name=txt)
            await update.message.reply_text("✅ ФИО сохранено")
            await show_form_step(update, context, lead_id, "city")
            return

        if step == "city":
            db_update_profile(lead_id, city=txt)
            await update.message.reply_text("✅ Город сохранён")
            await show_form_step(update, context, lead_id, "segment")
            return

        if step == "note":
            stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            db_append_note(lead_id, f"[{stamp}] {txt}")
            await update.message.reply_text("✅ Заметка сохранена")
            await show_form_step(update, context, lead_id, "done")
            return

    # обычные кнопки
    if txt == "🛒 Покупатели":
        await show_leads(update, context, 0, 20)
        return

    if txt == "🔔 Напоминания":
        rows = db_due_reminders(limit=30)
        if not rows:
            await update.message.reply_text("🔔 Сейчас нет просроченных напоминаний.")
            return
        lines = ["🔔 Пора связаться:\n"]
        for r in rows:
            lines.append(f"• {r.get('phone','—')} | {r.get('model_code') or '—'} | статус={r.get('status','—')} | id={r['id']}")
        await update.message.reply_text("\n".join(lines))
        return

    # кнопка каталога
    if txt == "📦 Каталог":
        await show_catalog(update, context)
        return

    await update.message.reply_text("Нажми «🛒 Покупатели» или /start")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.callback_query.answer("⛔ Нет доступа", show_alert=True)
        return

    data = update.callback_query.data or ""
    user_id = update.effective_user.id

    # навигация по каталогу
    if data == "catalog_back":
        await show_catalog(update, context)
        return

    if data.startswith("model:"):
        _, code = data.split(":", 1)
        await show_model(update, context, code)
        return

    # список лидов: навигация
    if data == "leads_back":
        await show_leads(update, context, 0, 20)
        return

    if data.startswith("leads:"):
        _, off, lim = data.split(":")
        await show_leads(update, context, int(off), int(lim))
        return

    if data.startswith("lead:"):
        lead_id = data.split(":", 1)[1]
        await show_lead_card(update, context, lead_id)
        return

    # анкета старт
    if data.startswith("lead_form:"):
        lead_id = data.split(":", 1)[1]
        await show_form_step(update, context, lead_id, "full_name")
        return

    # анкета: назад
    if data.startswith("form_back:"):
        _, lead_id, back_step = data.split(":", 2)
        await show_form_step(update, context, lead_id, back_step)
        return

    # анкета: пропустить
    if data.startswith("form_skip:"):
        lead_id = data.split(":", 1)[1]
        st = form_get(user_id)
        if not st or st.get("lead_id") != lead_id:
            await show_lead_card(update, context, lead_id)
            return

        step = st.get("step")
        if step == "full_name":
            await show_form_step(update, context, lead_id, "city")
            return
        if step == "city":
            await show_form_step(update, context, lead_id, "segment")
            return
        if step == "note":
            await show_form_step(update, context, lead_id, "done")
            return

        await show_form_step(update, context, lead_id, step)
        return

    # анкета: сегмент (тип клиента)
    if data.startswith("form_set_segment:"):
        _, lead_id, segment = data.split(":", 2)
        db_set_segment(lead_id, segment)
        await update.callback_query.answer("✅ Тип сохранён")
        await show_form_step(update, context, lead_id, "interest")
        return

    # анкета: интерес (галочки)
    if data.startswith("form_interest_toggle:"):
        _, lead_id, code = data.split(":", 2)
        key = (user_id, lead_id)
        selected = INTEREST_TMP.get(key, set())
        if code in selected:
            selected.remove(code)
        else:
            selected.add(code)
        INTEREST_TMP[key] = selected
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(reply_markup=interest_kb(user_id, lead_id))
        return

    if data.startswith("form_interest_clear:"):
        lead_id = data.split(":", 1)[1]
        INTEREST_TMP[(user_id, lead_id)] = set()
        await update.callback_query.answer("Очищено")
        await update.callback_query.edit_message_reply_markup(reply_markup=interest_kb(user_id, lead_id))
        return

    if data.startswith("form_interest_done:"):
        lead_id = data.split(":", 1)[1]
        selected = INTEREST_TMP.get((user_id, lead_id), set())
        db_update_profile(lead_id, interest=interest_codes_to_text(selected))
        await update.callback_query.answer("✅ Интерес сохранён")
        await show_form_step(update, context, lead_id, "status")
        return

    # анкета: статус
    if data.startswith("form_set_status:"):
        _, lead_id, status = data.split(":", 2)
        db_set_status(lead_id, status)
        await update.callback_query.answer("✅ Статус сохранён")
        await show_form_step(update, context, lead_id, "note")
        return

    # ручные действия из карточки
    if data.startswith("lead_status:"):
        lead_id = data.split(":", 1)[1]
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Выбери статус:", reply_markup=status_kb(lead_id))
        return

    if data.startswith("set_status:"):
        _, lead_id, status = data.split(":", 2)
        db_set_status(lead_id, status)
        await update.callback_query.answer("✅ Статус сохранён")
        await show_lead_card(update, context, lead_id)
        return

    if data.startswith("lead_segment:"):
        lead_id = data.split(":", 1)[1]
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Выбери сегмент:", reply_markup=segment_kb(lead_id))
        return

    if data.startswith("set_segment:"):
        _, lead_id, segment = data.split(":", 2)
        db_set_segment(lead_id, segment)
        await update.callback_query.answer("✅ Сегмент сохранён")
        await show_lead_card(update, context, lead_id)
        return

    if data.startswith("lead_note:"):
        lead_id = data.split(":", 1)[1]
        # кратко: используем анкетный шаг note
        form_set(user_id, lead_id, "note")
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("📝 Напиши заметку одним сообщением (или /start для выхода).")
        return

    if data.startswith("lead_remind:"):
        lead_id = data.split(":", 1)[1]
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("⏰ Выбери когда напомнить:", reply_markup=remind_kb(lead_id))
        return

    if data.startswith("set_remind:"):
        _, lead_id, mode = data.split(":", 2)
        now = datetime.now()
        if mode == "2h":
            dt = now + timedelta(hours=2)
            db_set_remind_at(lead_id, dt.isoformat())
        elif mode == "3d":
            dt = now + timedelta(days=3)
            db_set_remind_at(lead_id, dt.isoformat())
        elif mode == "tom11":
            dt = (now + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
            db_set_remind_at(lead_id, dt.isoformat())
        elif mode == "clear":
            db_set_remind_at(lead_id, None)

        await update.callback_query.answer("✅ Готово")
        await show_lead_card(update, context, lead_id)
        return

    await update.callback_query.answer()


def main():
    log.info("Starting bot...")

    # КЛЮЧЕВО: миграции на старте, чтобы не падало на “тип/сегмент”
    db_init()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()