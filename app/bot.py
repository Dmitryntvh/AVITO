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

# === ИМПОРТ БД ===
from app.db import list_leads, count_leads

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")


def get_admin_ids() -> set[int]:
    ids = set()
    for part in (ADMIN_TG_IDS_RAW or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = get_admin_ids()


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMIN_IDS)


# === КЛАВИАТУРЫ ===
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📥 Лиды"],
        ],
        resize_keyboard=True,
    )


def leads_keyboard(offset: int, limit: int, total: int) -> InlineKeyboardMarkup:
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


# === ФОРМАТ ВЫВОДА ===
def format_leads(leads, offset, limit, total) -> str:
    if not leads:
        return "Лидов пока нет."

    lines = [f"📥 Лиды {offset + 1}–{min(offset + limit, total)} из {total}\n"]

    for lead in leads:
        created = lead["created_at"]
        if isinstance(created, datetime):
            created = created.strftime("%d.%m.%Y %H:%M")

        lines.append(
            "\n".join(
                [
                    f"📞 {lead['phone']}",
                    f"Источник: {lead['source']}",
                    f"Модель: {lead['model_code'] or '-'}",
                    f"Дата: {created}",
                ]
            )
        )

    return "\n\n".join(lines)


# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        "CRM — управление лидами",
        reply_markup=main_keyboard(),
    )


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset=0, limit=20):
    total = count_leads()
    leads = list_leads(limit=limit, offset=offset)

    text = format_leads(leads, offset, limit, total)
    keyboard = leads_keyboard(offset, limit, total)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
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


# === ЗАПУСК ===
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling()


if __name__ == "__main__":
    main()
