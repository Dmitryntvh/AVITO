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

# ------------------------
# Logging
# ------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

# ------------------------
# ENV
# ------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set (Railway -> bot service -> Variables)")


def parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for p in (raw or "").split(","):
        p = p.strip()
        if p.isdigit():
            ids.add(int(p))
    return ids


ADMIN_IDS = parse_admin_ids(ADMIN_TG_IDS_RAW)


def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(u and u.id in ADMIN_IDS)


# ------------------------
# DB wrappers
# ------------------------
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


def db_append_note(lead_id: str, note_text: str):
    from app.db import append_lead_note
    return append_lead_note(lead_id, note_text)


def db_set_remind_at(lead_id: str, iso_or_none):
    from app.db import set_lead_remind_at
    return set_lead_remind_at(lead_id, iso_or_none)


def db_due_reminders(limit: int = 30):
    from app.db import due_reminders
    return due_reminders(limit=limit)


def db_update_profile(lead_id: str, full_name=None, city=None, interest=None):
    from app.db import update_lead_profile
    return update_lead_profile(lead_id, full_name=full_name, city=city, interest=interest)


# ------------------------
# UI helpers
# ------------------------
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📥 Лиды", "🔔 Напоминания"],
        ],
        resize_keyboard=True,
    )


STATUS_OPTIONS = [
    ("new", "🆕 Новый"),
    ("contact", "📞 Связаться"),
    ("work", "⚙️ В работе"),
    ("wait_pay", "💳 Ждёт оплату"),
    ("paid", "✅ Оплачен"),
    ("shipped", "📦 Отгружено"),
    ("lost", "👻 Пропал"),
    ("closed", "🗑 Закрыт"),
]

SEGMENT_OPTIONS = [
    ("unknown", "❓ Не задан"),
    ("private", "👤 Частник"),
    ("welder", "🧑‍🏭 Сварщик"),
    ("factory", "🏭 Производственник"),
]


def fmt_dt(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    return str(v) if v else "—"


def leads_list_kb(rows, offset: int, limit: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    for r in rows:
        lead_id = str(r["id"])
        phone = r.get("phone", "-")
        model = r.get("model_code") or "-"
        status = r.get("status", "new")
        buttons.append([InlineKeyboardButton(f"{phone} • {model} • {status}", callback_data=f"lead:{lead_id}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"leads:{max(offset - limit, 0)}:{limit}"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"leads:{offset + limit}:{limit}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def lead_card_text(lead: dict) -> str:
    return (
        f"👤 Лид\n\n"
        f"ID: {lead['id']}\n"
        f"📞 Телефон: {lead.get('phone','—')}\n"
        f"👤 ФИО: {lead.get('full_name') or '—'}\n"
        f"🏙 Город: {lead.get('city') or '—'}\n"
        f"🎯 Интерес: {lead.get('interest') or '—'}\n\n"
        f"Источник: {lead.get('source','—')}\n"
        f"Модель: {lead.get('model_code') or '—'}\n"
        f"Сегмент: {lead.get('segment','unknown')}\n"
        f"Статус: {lead.get('status','new')}\n\n"
        f"Создан: {fmt_dt(lead.get('created_at'))}\n"
        f"Последний контакт: {fmt_dt(lead.get('last_contact_at'))}\n"
        f"Напоминание: {fmt_dt(lead.get('remind_at'))}\n\n"
        f"📝 Заметки:\n{lead.get('note') or '—'}"
    )


def lead_card_kb(lead_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✍️ Данные (ФИО/город/интерес)", callback_data=f"lead_profile:{lead_id}"),
            ],
            [
                InlineKeyboardButton("🔁 Статус", callback_data=f"lead_status:{lead_id}"),
                InlineKeyboardButton("🏷 Сегмент", callback_data=f"lead_segment:{lead_id}"),
            ],
            [
                InlineKeyboardButton("📝 Заметка", callback_data=f"lead_note:{lead_id}"),
                InlineKeyboardButton("⏰ Напомнить", callback_data=f"lead_remind:{lead_id}"),
            ],
            [
                InlineKeyboardButton("⬅️ К списку", callback_data="leads_back"),
            ],
        ]
    )


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
                InlineKeyboardButton("✍️ Ввести вручную", callback_data=f"remind_manual:{lead_id}"),
            ],
            [
                InlineKeyboardButton("🧹 Убрать напоминание", callback_data=f"set_remind:{lead_id}:clear"),
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"lead:{lead_id}"),
            ],
        ]
    )


def profile_kb(lead_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👤 Ввести ФИО", callback_data=f"set_profile_mode:{lead_id}:full_name")],
            [InlineKeyboardButton("🏙 Ввести город", callback_data=f"set_profile_mode:{lead_id}:city")],
            [InlineKeyboardButton("🎯 Ввести интерес", callback_data=f"set_profile_mode:{lead_id}:interest")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"lead:{lead_id}")],
        ]
    )


# ------------------------
# Pending input state
# ------------------------
# user_id -> {"mode": "note"/"remind"/"profile", "lead_id": "...", "field": "..."}
PENDING = {}


# ------------------------
# Bot actions
# ------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    if not ADMIN_IDS:
        await update.message.reply_text("⚠️ ADMIN_TG_IDS не задан. Добавь его в Railway Variables (bot service).")
        return

    await update.message.reply_text("CRM-бот ✅", reply_markup=main_keyboard())


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, limit: int = 20):
    total = db_count_leads()
    rows = db_list_leads(limit=limit, offset=offset)
    text = f"📥 Лиды {offset + 1}–{min(offset + limit, total)} из {total}\nВыбери лид:"
    kb = leads_list_kb(rows, offset, limit, total)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def show_lead_card(update: Update, context: ContextTypes.DEFAULT_TYPE, lead_id: str):
    lead = db_get_lead(lead_id)
    if not lead:
        msg = "Лид не найден."
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


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    user_id = update.effective_user.id
    txt = (update.message.text or "").strip()

    # pending input modes
    if user_id in PENDING:
        mode = PENDING[user_id].get("mode")
        lead_id = PENDING[user_id].get("lead_id")

        if mode == "note":
            stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            db_append_note(lead_id, f"[{stamp}] {txt}")
            del PENDING[user_id]
            await update.message.reply_text("✅ Заметка сохранена.")
            await show_lead_card(update, context, lead_id)
            return

        if mode == "remind":
            try:
                dt = datetime.strptime(txt, "%d.%m.%Y %H:%M")
                db_set_remind_at(lead_id, dt.isoformat())
                del PENDING[user_id]
                await update.message.reply_text("✅ Напоминание установлено.")
                await show_lead_card(update, context, lead_id)
                return
            except ValueError:
                await update.message.reply_text("❌ Формат неверный. Нужно: ДД.ММ.ГГГГ ЧЧ:ММ (пример: 27.01.2026 18:30)")
                return

        if mode == "profile":
            field = PENDING[user_id].get("field")
            if field == "full_name":
                db_update_profile(lead_id, full_name=txt)
            elif field == "city":
                db_update_profile(lead_id, city=txt)
            elif field == "interest":
                db_update_profile(lead_id, interest=txt)

            del PENDING[user_id]
            await update.message.reply_text("✅ Сохранено.")
            await show_lead_card(update, context, lead_id)
            return

    # normal commands by buttons
    if txt == "📥 Лиды":
        await show_leads(update, context, offset=0, limit=20)
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

    await update.message.reply_text("Нажми кнопку «📥 Лиды» или /start")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.callback_query.answer("⛔ Нет доступа", show_alert=True)
        return

    data = update.callback_query.data or ""
    user_id = update.effective_user.id

    # back to list
    if data == "leads_back":
        await show_leads(update, context, offset=0, limit=20)
        return

    # list navigation
    if data.startswith("leads:"):
        _, off, lim = data.split(":")
        await show_leads(update, context, offset=int(off), limit=int(lim))
        return

    # open lead card
    if data.startswith("lead:"):
        lead_id = data.split(":", 1)[1]
        await show_lead_card(update, context, lead_id)
        return

    # profile menu
    if data.startswith("lead_profile:"):
        lead_id = data.split(":", 1)[1]
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("✍️ Какие данные заполнить?", reply_markup=profile_kb(lead_id))
        return

    if data.startswith("set_profile_mode:"):
        _, lead_id, field = data.split(":", 2)
        PENDING[user_id] = {"mode": "profile", "lead_id": lead_id, "field": field}
        await update.callback_query.answer()
        hint = {
            "full_name": "👤 Введи ФИО (пример: Иванов Иван Иванович)",
            "city": "🏙 Введи город (пример: Нижний Тагил)",
            "interest": "🎯 Введи интерес (пример: чертежи / заготовка / готовый чан)",
        }.get(field, "Введи значение")
        await update.callback_query.edit_message_text(hint)
        return

    # status menu
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

    # segment menu
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

    # note
    if data.startswith("lead_note:"):
        lead_id = data.split(":", 1)[1]
        PENDING[user_id] = {"mode": "note", "lead_id": lead_id}
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📝 Напиши заметку одним сообщением.\n"
            "Пример: «Хочет Polar-6, думает, перезвонить завтра»\n\n"
            "Отмена: /start"
        )
        return

    # remind menu
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

    if data.startswith("remind_manual:"):
        lead_id = data.split(":", 1)[1]
        PENDING[user_id] = {"mode": "remind", "lead_id": lead_id}
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "✍️ Введи дату и время в формате:\n"
            "ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Пример: 27.01.2026 18:30\n\n"
            "Отмена: /start"
        )
        return

    await update.callback_query.answer()


def main():
    log.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
