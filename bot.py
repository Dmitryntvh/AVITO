import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ===========================
# Загрузка каталога
# ===========================
with open("catalog.json", encoding="utf-8") as f:
    catalog = json.load(f)

# ===========================
# Корзина пользователей
# ===========================
user_carts = {}  # user_id: [{"name":..., "price":..., "qty":...}, ...]

# ===========================
# Клавиатуры
# ===========================
def main_menu_keyboard():
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in catalog.keys()]
    keyboard.append([InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")])
    return InlineKeyboardMarkup(keyboard)

def category_keyboard(cat_name):
    items = catalog[cat_name]
    keyboard = [[InlineKeyboardButton(item["name"], callback_data=f"item_{cat_name}_{i}")] 
                for i, item in enumerate(items)]
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def item_keyboard(cat_name, idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить в корзину", callback_data=f"add_{cat_name}_{idx}")],
        [InlineKeyboardButton("⬅ Назад к категории", callback_data=f"cat_{cat_name}")],
        [InlineKeyboardButton("⬅ Назад в главное меню", callback_data="back_main")]
    ])

def cart_keyboard(user_id):
    keyboard = []
    cart = user_carts.get(user_id, [])
    for i, item in enumerate(cart):
        keyboard.append([InlineKeyboardButton(f"Удалить {item['name']}", callback_data=f"del_{i}")])
    if cart:
        keyboard.append([InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")])
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

# ===========================
# Команда /start
# ===========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать! Выберите категорию товара:", 
        reply_markup=main_menu_keyboard()
    )

# ===========================
# Обработка кнопок
# ===========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    data = query.data
    
    # ------------------- категория -------------------
    if data.startswith("cat_"):
        cat_name = data[4:]
        await query.edit_message_text(
            f"Категория: {cat_name}\nВыберите товар:", 
            reply_markup=category_keyboard(cat_name)
        )
    
    # ------------------- товар -------------------
    elif data.startswith("item_"):
        _, cat_name, idx = data.split("_")
        idx = int(idx)
        item = catalog[cat_name][idx]
        await query.edit_message_media(
            media=InputMediaPhoto(media=item["photo"], caption=f"{item['name']}\nЦена: {item['price']}"),
            reply_markup=item_keyboard(cat_name, idx)
        )
    
    # ------------------- добавление в корзину -------------------
    elif data.startswith("add_"):
        _, cat_name, idx = data.split("_")
        idx = int(idx)
        item = catalog[cat_name][idx]
        cart = user_carts.get(user_id, [])
        found = False
        for c in cart:
            if c["name"] == item["name"]:
                c["qty"] += 1
                found = True
                break
        if not found:
            cart.append({"name": item["name"], "price": item["price"], "qty": 1})
        user_carts[user_id] = cart
        await query.edit_message_caption(
            caption=f"{item['name']}\nЦена: {item['price']}\n✅ Добавлено в корзину",
            reply_markup=item_keyboard(cat_name, idx)
        )
    
    # ------------------- просмотр корзины -------------------
    elif data == "view_cart":
        cart = user_carts.get(user_id, [])
        if not cart:
            text = "Корзина пуста"
        else:
            text = "Ваша корзина:\n"
            for i, item in enumerate(cart):
                text += f"{i+1}. {item['name']} - {item['price']} x {item['qty']}\n"
        await query.edit_message_text(
            text=text,
            reply_markup=cart_keyboard(user_id)
        )
    
    # ------------------- удаление из корзины -------------------
    elif data.startswith("del_"):
        idx = int(data[4:])
        cart = user_carts.get(user_id, [])
        if 0 <= idx < len(cart):
            del cart[idx]
            user_carts[user_id] = cart
        await query.edit_message_text(
            text="Корзина обновлена" if cart else "Корзина пуста",
            reply_markup=cart_keyboard(user_id)
        )
    
    # ------------------- оформление заказа -------------------
    elif data == "checkout":
        cart = user_carts.get(user_id, [])
        if not cart:
            await query.edit_message_text("Корзина пуста")
            return
        text = "Новый заказ:\n"
        total_items = 0
        for item in cart:
            text += f"{item['name']} - {item['price']} x {item['qty']}\n"
            total_items += item['qty']
        text += f"\nИтого товаров: {total_items}"
        # Очистка корзины
        user_carts[user_id] = []
        await query.edit_message_text(f"{text}\n✅ Заказ оформлен", reply_markup=main_menu_keyboard())
    
    # ------------------- назад в главное меню -------------------
    elif data == "back_main":
        await query.edit_message_text(
            "Главное меню. Выберите категорию:", 
            reply_markup=main_menu_keyboard()
        )

# ===========================
# Запуск бота
# ===========================
if __name__ == "__main__":
    TOKEN = "8067476607:AAEhhNL6YISLFR9cj0ZUYquwkeI3FNFZAl8"  # Вставьте токен вашего бота
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Бот запущен...")
    app.run_polling()
