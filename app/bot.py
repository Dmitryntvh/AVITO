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

# ВАЖНО: импортируем функции из твоего app/db.py
from app.db import list_leads, count_leads

BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # токен бота
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "")  # тот же список, что и для админки сайта


def admin_ids() -> set[int]:
    ids = set()
    for p in (ADMIN_TG_IDS_RAW or "").split(","):
        p = p.strip()
        if p.isdigit():
            ids.add(int(p))
    return ids


ADMINS = admin_ids()


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMINS)


def main_keyboard() -> ReplyKeyboardMarkup:
    # Обычные кнопки (не inline)
    return ReplyKeyboardMarkup(
        [
            ["📥 Лиды", "🔎 Поиск"],
            ["➕ Добавить заметку", "⚙️ Настройки"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def format_leads(rows, offset: int, limit: int, total: int) -> str:
    if not rows:
        return "Лидов пока нет."

    lines = []
    end = min(offset + limit, total)
    lines.append(f"📥 Лиды: {offset + 1}–{end} из {total}\n")

    for r in rows:
        created = r.get("created_at")
        if isinstance(created, datetime):
            created_str = created.strftime("%Y-%m-%d %H:%M")
        else:
            created_str = str(created)

        phone = r.get("phone", "")
        src = r.get("source", "")
        model = r.get("model_code") or "-"

        lines.append(
            "\n".join(
                [
                    f"📞 {phone}",
                    f"Источник: {src}",
                    f"Модель: {model}",
                    f"Дата: {created_str}",
                ]
            )
        )

    return "\n\n".join(lines)


def leads_nav_keyboard(offset: int, limit: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    prev_offset = max(offset - limit, 0)
    next_offset = offset + limit

    row = []
    if offset > 0:
        row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"leads:{prev_offset}:{limit}"))
    if next_offset < total:
        row.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"leads:{next_offset}:{limit}"))
    if row:
        buttons.append(row)

    # Быстрые лимиты
    buttons.append(
        [
            InlineKeyboardButton("Показать 20", callback_data=f"leads:{offset}:20"),
            InlineKeyboardButton("50", callback_data=f"leads:{offset}:50"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


async def send_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, limit: int = 20):
    total = count_leads()
    rows = list_leads(limit=limit, offset=offset)
    text = format_leads(rows, offset=offset, limit=limit, total=total)

    kb = leads_nav_keyboard(offset=offset, limit=limit, total=total)

    # Если это callback — редактируем сообщение
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ запрещён.")
        return

    await update.message.reply_text(
        "Панель управления CRM.\nВыбери действие кнопкой ниже:",
        reply_markup=main_keyboard(),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ запрещён.")
        return

    text = (update.message.text or "").strip()

    if text == "📥 Лиды":
        await send_leads(update, context, offset=0, limit=20)
        return

    await update.message.reply_text("Команда не распознана. Нажми кнопку «📥 Лиды» или /start.")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.callback_query.answer("Доступ запрещён.", show_alert=True)
        return

    data = update.callback_query.data or ""

    # leads:OFFSET:LIMIT
    if data.startswith("leads:"):
        try:
            _, offset_str, limit_str = data.split(":")
            offset = int(offset_str)
            limit = int(limit_str)
        except Exception:
            await update.callback_query.answer("Ошибка пагинации", show_alert=True)
            return

        await send_leads(update, context, offset=offset, limit=limit)
        return

    await update.callback_query.answer()


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return application


if __name__ == "__main__":
    app = build_app()
    # Для простоты: polling (для Railway лучше webhook, но кнопку лидов это не меняет)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
