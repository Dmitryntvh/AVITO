import os
import logging
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

# =========================
# LOGGING (видно в Railway)
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")


# =========================
# ENV
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_TG_IDS_RAW = os.getenv("ADMIN_TG_IDS", "").strip()

# ВАЖНО: бот не должен "тихо" падать — если токена нет, это фатально.
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set (Railway -> bot service -> Variables)")


def parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = parse_admin_ids(ADMIN_TG_IDS_RAW)


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMIN_IDS)


# =========================
# DB helpers (ленивые)
# =========================
def safe_db_count_leads() -> int:
    """
    Не валит бота, даже если БД не доступна/не настроена.
    """
    try:
        from app.db import count_leads  # импорт только когда надо
        return int(count_leads())
    except Exception as e:
        log.exception("count_leads failed: %s", e)
        return -1  # признак ошибки


def safe_db_list_leads(limit: int, offset: int):
    try:
        from app.db import list_leads
        return list_leads(limit=limit, offset=offset)
    except Exception as e:
        log.exception("list_leads failed: %s", e)
        return None


# =========================
# UI
# =========================
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📥 Лиды"],
        ],
        resize_keyboard=True,
    )


def leads_keyboard(offset: int, limit: int, total: int) -> InlineKeyboardMarkup | None:
    buttons = []

    if offset > 0:
        buttons.append(
            InlineKeyboardButton("◀️ Назад", callback_data=f"leads:{max(offset - limit, 0)}:{limit}")
        )
    if offset + limit < total:
        buttons.append(
            InlineKeyboardButton("▶️ Вперёд", callback_data=f"leads:{offset + limit}:{limit}")
        )

    if buttons:
        return InlineKeyboardMarkup([buttons])

    return None


def format_leads(rows, offset: int, limit: int, total: int) -> str:
    if not rows:
        return "Лидов пока нет."

    end = min(offset + limit, total)
    out = [f"📥 Лиды {offset + 1}–{end} из {total}\n"]

    for r in rows:
        created = r.get("created_at")
        if isinstance(created, datetime):
            created_str = created.strftime("%d.%m.%Y %H:%M")
        else:
            created_str = str(created) if created is not None else "-"

        out.append(
            "\n".join(
                [
                    f"📞 {r.get('phone', '-')}",
                    f"Источник: {r.get('source', '-')}",
                    f"Модель: {r.get('model_code') or '-'}",
                    f"Дата: {created_str}",
                ]
            )
        )

    return "\n\n".join(out)


# =========================
# Handlers
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    if not ADMIN_IDS:
        await update.message.reply_text(
            "⚠️ ADMIN_TG_IDS не задан.\n"
            "Добавь переменную ADMIN_TG_IDS в Railway (bot service → Variables)."
        )
        return

    await update.message.reply_text(
        "CRM-бот запущен ✅\nНажми «📥 Лиды»",
        reply_markup=main_keyboard(),
    )


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, limit: int = 20):
    if not is_admin(update):
        # если это callback — отвечаем алертом
        if update.callback_query:
            await update.callback_query.answer("⛔ Доступ запрещён", show_alert=True)
        else:
            await update.message.reply_text("⛔ Доступ запрещён.")
        return

    total = safe_db_count_leads()
    if total < 0:
        # Ошибка БД
        msg = (
            "❌ Не могу прочитать лиды из базы.\n\n"
            "Проверь в Railway (bot service → Variables):\n"
            "• DATABASE_URL (должен быть как у web)\n\n"
            "И проверь, что таблицы созданы (web уже создаёт init_db на старте)."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    rows = safe_db_list_leads(limit=limit, offset=offset)
    if rows is None:
        msg = (
            "❌ Ошибка чтения лидов.\n"
            "Смотри логи Railway bot-service (там будет Traceback)."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    text = format_leads(rows, offset=offset, limit=limit, total=total)
    kb = leads_keyboard(offset=offset, limit=limit, total=total)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if update.message.text == "📥 Лиды":
        await show_leads(update, context, offset=0, limit=20)
        return

    await update.message.reply_text("Нажми «📥 Лиды» или отправь /start")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        return

    data = update.callback_query.data or ""
    if data.startswith("leads:"):
        try:
            _, offset_str, limit_str = data.split(":")
            offset = int(offset_str)
            limit = int(limit_str)
        except Exception:
            await update.callback_query.answer("Ошибка пагинации", show_alert=True)
            return

        await show_leads(update, context, offset=offset, limit=limit)
        return

    await update.callback_query.answer()


def main():
    log.info("Starting bot...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
