import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiosqlite

# ВАШ ТОКЕН
BOT_TOKEN = "8067476607:AAEhhNL6YISLFR9cj0ZUYquwkeI3FNFZAl8"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "banya_catalog.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT NOT NULL,
            description TEXT, specs TEXT, price_project TEXT, price_welding TEXT,
            price_finish TEXT, price_ladder TEXT, avito_link TEXT, ozon_link TEXT,
            phone TEXT, photo_id TEXT, FOREIGN KEY (category_id) REFERENCES categories(id))""")
        await db.commit()

def get_main_menu():
    kb = [
        [KeyboardButton(text="📖 Смотреть каталог")],
        [KeyboardButton(text="➕ Категория"), KeyboardButton(text="➕ Товар")],
        [KeyboardButton(text="✏️ Изменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_edit_menu():
    kb = [
        [KeyboardButton(text="🗑 Удалить категорию"), KeyboardButton(text="✏️ Изменить категорию")],
        [KeyboardButton(text="🗑 Удалить товар"), KeyboardButton(text="✏️ Изменить товар")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_categories_inline(categories):
    kb = [[InlineKeyboardButton(text=cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
    kb.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_products_inline(products, category_id):
    kb = [[InlineKeyboardButton(text=prod[2], callback_data=f"prod_{prod[0]}_{category_id}")] for prod in products]
    kb.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_cats")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Состояния для добавления категории
class AddCategoryState(StatesGroup):
    name = State()
    description = State()

# Состояния для добавления товара
class AddProductState(StatesGroup):
    category, name, description, specs = State(), State(), State(), State()
    price_project, price_welding, price_finish, price_ladder = State(), State(), State(), State()
    avito, ozon, phone, photo = State(), State(), State(), State()

# Состояния для удаления/изменения
class DeleteCategoryState(StatesGroup):
    category = State()

class EditCategoryState(StatesGroup):
    category, new_name, new_description = State(), State(), State()

class DeleteProductState(StatesGroup):
    category, product = State(), State()

class EditProductState(StatesGroup):
    category, product, field, value = State(), State(), State(), State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я бот-каталог банных чанов.\nВыберите действие:", reply_markup=get_main_menu())

@dp.message(F.text == "📖 Смотреть каталог")
async def show_catalog(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as cursor:
            categories = await cursor.fetchall()
    if not categories:
        await message.answer("📭 Каталог пуст. Сначала создайте категорию через меню '➕ Категория'.")
        return
    kb = [[InlineKeyboardButton(text=cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
    kb.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_menu")])
    await message.answer("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "back_cats")
async def back_to_categories(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as cursor:
            categories = await cursor.fetchall()
    kb = [[InlineKeyboardButton(text=cat[1], callback_data=f"cat_{cat[0]}")] for cat in categories]
    kb.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_menu")])
    await callback.message.edit_text("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "back_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

@dp.callback_query(F.data.startswith("cat_"))
async def show_category_products(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM products WHERE category_id = ?", (cat_id,)) as cursor:
            products = await cursor.fetchall()
        async with db.execute("SELECT name FROM categories WHERE id = ?", (cat_id,)) as cursor:
            cat_name = (await cursor.fetchone())[0]
    if not products:
        await callback.answer("Нет товаров в этой категории.", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=prod[2], callback_data=f"prod_{prod[0]}_{cat_id}")] for prod in products]
    kb.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_cats")])
    await callback.message.edit_text(f"📦 Товары '{cat_name}':", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("prod_"))
async def show_product_detail(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    prod_id, cat_id = int(parts[1]), int(parts[2])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)) as cursor:
            p = await cursor.fetchone()
    if not p: return
    
    text = f"🔥 <b>{p[2]}</b>\n\n"
    if p[3]: text += f"📝 <b>Описание:</b>\n{p[3]}\n\n"
    if p[4]: text += f"⚙️ <b>Характеристики:</b>\n<pre>{p[4]}</pre>\n\n"
    text += "💰 <b>Комплектация:</b>\n"
    if p[5]: text += f"▫️ Проект: {p[5]}\n"
    if p[6]: text += f"▫️ Сварка: {p[6]}\n"
    if p[7]: text += f"▫️ Отделка: {p[7]}\n"
    if p[8]: text += f"▫️ Лестница: {p[8]}\n"
    if p[9]: text += f"\n📍 <a href='{p[9]}'>Авито</a>"
    if p[10]: text += f" | <a href='{p[10]}'>Ozon</a>"
    if p[11]: text += f"\n📞 {p[11]}"

    kb = []
    if p[11]:
        kb.append([InlineKeyboardButton(text="📞 Позвонить", url=f"tel:{''.join(filter(str.isdigit, p[11]))}")])
    if p[9]: kb.append([InlineKeyboardButton(text="📲 Авито", url=p[9])])
    if p[10]: kb.append([InlineKeyboardButton(text="📦 Ozon", url=p[10])])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"cat_{cat_id}")])
    
    try:
        if p[12]:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
            await bot.send_photo(callback.message.chat.id, p[12], reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except: pass

# === ДОБАВЛЕНИЕ КАТЕГОРИИ ===
@dp.message(F.text == "➕ Категория")
async def start_add_category(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой категории (например: ПОЛЯРНЫЕ):")
    await state.set_state(AddCategoryState.name)

@dp.message(AddCategoryState.name)
async def process_cat_name(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": 
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    await state.update_data(name=message.text)
    await message.answer("Введите описание категории (или 'нет'):")
    await state.set_state(AddCategoryState.description)

@dp.message(AddCategoryState.description)
async def process_cat_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    desc = message.text if message.text.lower() != "нет" else ""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (data['name'], desc))
            await db.commit()
        await state.clear()
        await message.answer(f"✅ Категория '{data['name']}' создана!", reply_markup=get_main_menu())
    except Exception as e:
        await message.answer(f"Ошибка: категория с таким именем уже существует. Попробуйте другое название.")
        await state.clear()

# === ДОБАВЛЕНИЕ ТОВАРА ===
@dp.message(F.text == "➕ Товар")
async def start_add_product(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as cursor: 
            categories = await cursor.fetchall()
    if not categories:
        await message.answer("Сначала создайте категорию через меню '➕ Категория'!")
        return
    kb = [[KeyboardButton(text=c[1])] for c in categories] + [[KeyboardButton(text="❌ Отмена")]]
    await message.answer("Выберите категорию для товара:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
    await state.set_state(AddProductState.category)

@dp.message(AddProductState.category)
async def process_category(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": 
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM categories WHERE name = ?", (message.text,)) as c: 
            res = await c.fetchone()
    if res:
        await state.update_data(category_id=res[0])
        await message.answer("Название модели (напр. ПОЛЯРНЫЙ 6 Type B):")
        await state.set_state(AddProductState.name)

@dp.message(AddProductState.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Описание:")
    await state.set_state(AddProductState.description)

@dp.message(AddProductState.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Характеристики (списком, как в примере):")
    await state.set_state(AddProductState.specs)

@dp.message(AddProductState.specs)
async def process_specs(message: types.Message, state: FSMContext):
    await state.update_data(specs=message.text)
    await message.answer("Цена проекта (или 'нет'):")
    await state.set_state(AddProductState.price_project)

async def next_step(message: types.Message, state: FSMContext, key: str, next_state: State):
    val = message.text if message.text.lower() != "нет" else None
    await state.update_data(**{key: val})
    labels = {
        'price_project': 'цену проекта',
        'price_welding': 'цену заготовки для сварки',
        'price_finish': 'цену заготовки для отделки',
        'price_ladder': 'цену заготовки для лестницы',
        'avito_link': 'ссылку на Авито (или "нет")',
        'ozon_link': 'ссылку на Ozon (или "нет")'
    }
    await message.answer(f"Введите {labels.get(key, key)}:")
    await state.set_state(next_state)

@dp.message(AddProductState.price_project)
async def pp(message: types.Message, state: FSMContext): 
    await next_step(message, state, 'price_project', AddProductState.price_welding)

@dp.message(AddProductState.price_welding)
async def pw(message: types.Message, state: FSMContext): 
    await next_step(message, state, 'price_welding', AddProductState.price_finish)

@dp.message(AddProductState.price_finish)
async def pf(message: types.Message, state: FSMContext): 
    await next_step(message, state, 'price_finish', AddProductState.price_ladder)

@dp.message(AddProductState.price_ladder)
async def pl(message: types.Message, state: FSMContext): 
    await next_step(message, state, 'price_ladder', AddProductState.avito)

@dp.message(AddProductState.avito)
async def pa(message: types.Message, state: FSMContext): 
    await next_step(message, state, 'avito_link', AddProductState.ozon)

@dp.message(AddProductState.ozon)
async def po(message: types.Message, state: FSMContext): 
    await state.update_data(ozon_link=(message.text if message.text.lower() != "нет" else None))
    await message.answer("Контактный телефон:")
    await state.set_state(AddProductState.phone)

@dp.message(AddProductState.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Фото товара (отправьте изображением) или напишите 'нет':")
    await state.set_state(AddProductState.photo)

@dp.message(AddProductState.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id if message.photo else None
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO products (category_id, name, description, specs, price_project, price_welding, price_finish, price_ladder, avito_link, ozon_link, phone, photo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data['category_id'], data['name'], data['description'], data['specs'], 
             data.get('price_project'), data.get('price_welding'), data.get('price_finish'), 
             data.get('price_ladder'), data.get('avito_link'), data.get('ozon_link'), 
             data['phone'], photo_id))
        await db.commit()
    await state.clear()
    await message.answer("✅ Товар добавлен!", reply_markup=get_main_menu())

@dp.message(F.text == "✏️ Изменить")
async def show_edit_menu(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_edit_menu())

@dp.message(F.text == "🔙 Назад в меню")
async def back_main(message: types.Message):
    await cmd_start(message)

# === УДАЛЕНИЕ КАТЕГОРИИ ===
@dp.message(F.text == "🗑 Удалить категорию")
async def start_delete_category(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as c: 
            cats = await c.fetchall()
    if not cats:
        await message.answer("Нет категорий для удаления.")
        return
    kb = [[KeyboardButton(text=c[1])] for c in cats] + [[KeyboardButton(text="❌ Отмена")]]
    await message.answer("Выберите категорию для удаления (вместе со всеми товарами):", 
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
    await state.set_state(DeleteCategoryState.category)

@dp.message(DeleteCategoryState.category)
async def del_category(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM categories WHERE name=?", (message.text,)) as c: 
            r = await c.fetchone()
        if r:
            cid = r[0]
            await db.execute("DELETE FROM products WHERE category_id=?", (cid,))
            await db.execute("DELETE FROM categories WHERE id=?", (cid,))
            await db.commit()
            await state.clear()
            await message.answer(f"✅ Категория '{message.text}' удалена!", reply_markup=get_main_menu())

# === ИЗМЕНЕНИЕ КАТЕГОРИИ ===
@dp.message(F.text == "✏️ Изменить категорию")
async def start_edit_category(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as c: 
            cats = await c.fetchall()
    if not cats:
        await message.answer("Нет категорий для изменения.")
        return
    kb = [[KeyboardButton(text=c[1])] for c in cats] + [[KeyboardButton(text="❌ Отмена")]]
    await message.answer("Выберите категорию для изменения:", 
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
    await state.set_state(EditCategoryState.category)

@dp.message(EditCategoryState.category)
async def edit_cat_select(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM categories WHERE name=?", (message.text,)) as c: 
            r = await c.fetchone()
    if r:
        await state.update_data(cat_id=r[0], old_name=message.text)
        await message.answer("Введите новое название категории (или 'нет' чтобы не менять):")
        await state.set_state(EditCategoryState.new_name)

@dp.message(EditCategoryState.new_name)
async def edit_cat_name(message: types.Message, state: FSMContext):
    if message.text.lower() != "нет":
        await state.update_data(new_name=message.text)
    await message.answer("Введите новое описание (или 'нет' чтобы не менять):")
    await state.set_state(EditCategoryState.new_description)

@dp.message(EditCategoryState.new_description)
async def edit_cat_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    updates = []
    values = []
    if data.get('new_name'):
        updates.append("name=?")
        values.append(data['new_name'])
    if message.text.lower() != "нет":
        updates.append("description=?")
        values.append(message.text)
    
    if updates:
        values.append(data['cat_id'])
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(f"UPDATE categories SET {','.join(updates)} WHERE id=?", values)
            await db.commit()
        await message.answer("✅ Категория обновлена!", reply_markup=get_main_menu())
    else:
        await message.answer("Ничего не изменено.", reply_markup=get_main_menu())
    await state.clear()

# === УДАЛЕНИЕ ТОВАРА ===
@dp.message(F.text == "🗑 Удалить товар")
async def start_delete_product(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as c: 
            cats = await c.fetchall()
    if not cats:
        await message.answer("Нет категорий.")
        return
    kb = [[KeyboardButton(text=c[1])] for c in cats] + [[KeyboardButton(text="❌ Отмена")]]
    await message.answer("Выберите категорию:", 
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
    await state.set_state(DeleteProductState.category)

@dp.message(DeleteProductState.category)
async def del_prod_cat(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM categories WHERE name=?", (message.text,)) as c: 
            r = await c.fetchone()
        if r:
            cid = r[0]
            async with db.execute("SELECT id, name FROM products WHERE category_id=?", (cid,)) as c: 
                prods = await c.fetchall()
            if prods:
                kb = [[KeyboardButton(text=p[1])] for p in prods] + [[KeyboardButton(text="❌ Отмена")]]
                await state.update_data(cat_id=cid)
                await message.answer("Выберите товар для удаления:", 
                                     reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
                await state.set_state(DeleteProductState.product)
            else:
                await message.answer("В этой категории нет товаров.", reply_markup=get_main_menu())
                await state.clear()

@dp.message(DeleteProductState.product)
async def del_product(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM products WHERE name=? AND category_id=?", 
                              (message.text, data['cat_id'])) as c: 
            r = await c.fetchone()
        if r:
            await db.execute("DELETE FROM products WHERE id=?", (r[0],))
            await db.commit()
            await state.clear()
            await message.answer("✅ Товар удален!", reply_markup=get_main_menu())

# === ИЗМЕНЕНИЕ ТОВАРА ===
@dp.message(F.text == "✏️ Изменить товар")
async def start_edit_product(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM categories") as c: 
            cats = await c.fetchall()
    if not cats:
        await message.answer("Нет категорий.")
        return
    kb = [[KeyboardButton(text=c[1])] for c in cats] + [[KeyboardButton(text="❌ Отмена")]]
    await message.answer("Выберите категорию:", 
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
    await state.set_state(EditProductState.category)

@dp.message(EditProductState.category)
async def edit_prod_cat(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM categories WHERE name=?", (message.text,)) as c: 
            r = await c.fetchone()
        if r:
            cid = r[0]
            async with db.execute("SELECT id, name FROM products WHERE category_id=?", (cid,)) as c: 
                prods = await c.fetchall()
            if prods:
                kb = [[KeyboardButton(text=p[1])] for p in prods] + [[KeyboardButton(text="❌ Отмена")]]
                await state.update_data(cat_id=cid)
                await message.answer("Выберите товар для изменения:", 
                                     reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
                await state.set_state(EditProductState.product)
            else:
                await message.answer("В этой категории нет товаров.", reply_markup=get_main_menu())
                await state.clear()

@dp.message(EditProductState.product)
async def edit_prod_select(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM products WHERE name=? AND category_id=?", 
                              (message.text, data['cat_id'])) as c: 
            r = await c.fetchone()
    if r:
        await state.update_data(prod_id=r[0])
        fields = [
            "Название", "Описание", "Характеристики", 
            "Цена проекта", "Цена сварки", "Цена отделки", "Цена лестницы",
            "Ссылка Авито", "Ссылка Ozon", "Телефон"
        ]
        kb = [[KeyboardButton(text=f)] for f in fields] + [[KeyboardButton(text="❌ Отмена")]]
        await message.answer("Какое поле изменить?", 
                             reply_markup=ReplyKeyboardMarkup(keyboard=kb, one_time_keyboard=True))
        await state.set_state(EditProductState.field)

@dp.message(EditProductState.field)
async def edit_prod_field(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отмена", reply_markup=get_main_menu())
        return
    
    field_map = {
        "Название": "name",
        "Описание": "description",
        "Характеристики": "specs",
        "Цена проекта": "price_project",
        "Цена сварки": "price_welding",
        "Цена отделки": "price_finish",
        "Цена лестницы": "price_ladder",
        "Ссылка Авито": "avito_link",
        "Ссылка Ozon": "ozon_link",
        "Телефон": "phone"
    }
    
    if message.text in field_map:
        await state.update_data(field=field_map[message.text])
        await message.answer(f"Введите новое значение для '{message.text}':")
        await state.set_state(EditProductState.value)

@dp.message(EditProductState.value)
async def edit_prod_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data['field']
    value = message.text
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, data['prod_id']))
        await db.commit()
    
    await state.clear()
    await message.answer("✅ Товар обновлен!", reply_markup=get_main_menu())

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
