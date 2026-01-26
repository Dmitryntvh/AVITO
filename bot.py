import os
from datetime import datetime

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

from app.db import list_leads, count_leads

# =====================
# ENV
# =====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")


def get_admin_ids():
    ids = set()
    for x in (ADMIN_TG_IDS_RAW or "").split(","):
        x = x.strip()
        if x.isdigit():
            ids.add(int(x))
    return ids


ADMIN_IDS = get_admin_ids()


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMIN_IDS)


# =====================
# UI
# =====================
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📥 Лиды"]],
        resize_keyboard=True,
    )


def leads_keyboard(offset: int, limit: int, total: int):
    buttons = []

    if offset > 0:
        buttons.append(
            InlineKeyboardButton("◀️ Назад", callback_data=f"leads:{offset - limit}:{limit}")
        )

    if offset + limit < total:
        buttons.append(
            InlineKeyboardButton("▶️ Вперёд", callback_data=f"leads:{offset + limit}:{limit}")
        )

    return InlineKeyboardMarkup([buttons]) if buttons else None


def format_leads(rows, offset, limit, total):
    if not rows:
        return "Лидов пока нет."

    out = [f"📥 Лиды {offset + 1}–{min(offset + limit, total)} из {total}\n"]

    for r in rows:
        dt = r["created_at"]
        if isinstance(dt, datetime):
            dt = dt.strftime("%d.%m.%Y %H:%M")

        out.append(
            "\n".join(
                [
                    f"📞 {r['phone']}",
                    f"Источник: {r['source']}",
                    f"Модель: {r['model_code'] or '-'}",
                    f"Дата: {dt}",
                ]
            )
        )

    return "\n\n".join(out)


# =====================
# HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update.message.reply_text(
        "CRM • Управление лидами",
        reply_markup=main_keyboard(),
    )


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset=0, limit=20):
    total = count_leads()
    leads = list_leads(limit=limit, offset=offset)

    text = format_leads(leads, offset, limit, total)
    kb = leads_keyboard(offset, limit, total)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    if update.message.text == "📥 Лиды":
        await show_leads(update, context)
        return

    await update.message.reply_text("Нажми кнопку 📥 Лиды или /start")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.callback_query.answer("⛔ Нет доступа", show_alert=True)
        return

    data = update.callback_query.data

    if data.startswith("leads:"):
        _, offset, limit = data.split(":")
        await show_leads(update, context, int(offset), int(limit))


# =====================
# RUN
# =====================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling()


if __name__ == "__main__":
    main()
