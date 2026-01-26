import os
import uuid
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


# =========================
# Connection
# =========================
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# =========================
# Init / migrations (safe)
# =========================
def init_db():
    """
    Создаёт таблицы (если их нет) и добавляет новые колонки в leads (если их нет).
    Можно вызывать на старте приложения сколько угодно раз.
    """

    create_sql = """
    -- Лиды (мини CRM)
    CREATE TABLE IF NOT EXISTS leads (
      id UUID PRIMARY KEY,
      phone TEXT NOT NULL,
      source TEXT NOT NULL,
      model_code TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Каталог моделей
    CREATE TABLE IF NOT EXISTS catalog_models (
      code TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      short TEXT NOT NULL DEFAULT '',
      price_drawings INTEGER NOT NULL DEFAULT 0,
      drawings_url TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Комплекты (заготовки)
    CREATE TABLE IF NOT EXISTS catalog_kits (
      id UUID PRIMARY KEY,
      model_code TEXT NOT NULL REFERENCES catalog_models(code) ON DELETE CASCADE,
      material TEXT NOT NULL,
      price INTEGER NOT NULL DEFAULT 0
    );

    -- Фото (URL) для моделей
    CREATE TABLE IF NOT EXISTS catalog_images (
      id UUID PRIMARY KEY,
      model_code TEXT NOT NULL REFERENCES catalog_models(code) ON DELETE CASCADE,
      url TEXT NOT NULL,
      sort_order INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_catalog_kits_model ON catalog_kits(model_code);
    CREATE INDEX IF NOT EXISTS idx_catalog_images_model ON catalog_images(model_code);
    """

    migrate_leads_sql = [
        # расширяем leads (если колонок нет - добавим)
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS name TEXT;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS segment TEXT NOT NULL DEFAULT 'unknown';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS note TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMPTZ;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS remind_at TIMESTAMPTZ;",
        # индексы
        "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);",
        "CREATE INDEX IF NOT EXISTS idx_leads_segment ON leads(segment);",
        "CREATE INDEX IF NOT EXISTS idx_leads_remind_at ON leads(remind_at);",
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for stmt in migrate_leads_sql:
                cur.execute(stmt)
        conn.commit()


# =========================
# Leads (CRM)
# =========================
def insert_lead(phone, source, model_code=None, name=None):
    """
    Создаёт лида. Возвращает строку UUID.
    phone: +7...
    source: 'qr'/'avito'/'ozon'/etc
    model_code: например 'polar-6'
    name: опционально
    """
    lead_id = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (id, phone, source, model_code, name)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (lead_id, phone, source, model_code, name),
            )
        conn.commit()
    return str(lead_id)


def count_leads():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM leads")
            row = cur.fetchone()
            return int(row["cnt"])


def list_leads(limit=20, offset=0):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, phone, source, model_code, created_at, status, segment
                FROM leads
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return cur.fetchall()


def get_lead(lead_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, phone, source, model_code, created_at,
                       name, segment, status, note, last_contact_at, remind_at
                FROM leads
                WHERE id = %s
                """,
                (lead_id,),
            )
            return cur.fetchone()


def set_lead_status(lead_id, status):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET status = %s,
                    last_contact_at = NOW()
                WHERE id = %s
                """,
                (status, lead_id),
            )
        conn.commit()


def set_lead_segment(lead_id, segment):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET segment = %s,
                    last_contact_at = NOW()
                WHERE id = %s
                """,
                (segment, lead_id),
            )
        conn.commit()


def append_lead_note(lead_id, note_text):
    """
    Добавляет заметку в начало поля note (чтобы последние были сверху).
    """
    note_text = (note_text or "").strip()
    if not note_text:
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET note = CASE
                    WHEN note = '' THEN %s
                    ELSE %s || E'\n\n' || note
                END,
                last_contact_at = NOW()
                WHERE id = %s
                """,
                (note_text, note_text, lead_id),
            )
        conn.commit()


def set_lead_remind_at(lead_id, remind_at_iso_or_none):
    """
    remind_at_iso_or_none:
      - None -> очистить напоминание
      - ISO строка (например dt.isoformat()) -> установить
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if remind_at_iso_or_none:
                cur.execute(
                    "UPDATE leads SET remind_at = %s WHERE id = %s",
                    (remind_at_iso_or_none, lead_id),
                )
            else:
                cur.execute(
                    "UPDATE leads SET remind_at = NULL WHERE id = %s",
                    (lead_id,),
                )
        conn.commit()


def due_reminders(limit=20):
    """
    Лиды, по которым уже пора напомнить (remind_at <= now).
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, phone, source, model_code, remind_at, status, segment
                FROM leads
                WHERE remind_at IS NOT NULL AND remind_at <= NOW()
                ORDER BY remind_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


# =========================
# Catalog
# =========================
def list_models():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, name, short, price_drawings, drawings_url, updated_at
                FROM catalog_models
                ORDER BY updated_at DESC
                """
            )
            return cur.fetchall()


def get_model(code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, name, short, price_drawings, drawings_url
                FROM catalog_models
                WHERE code = %s
                """,
                (code,),
            )
            model = cur.fetchone()
            if not model:
                return None

            cur.execute(
                """
                SELECT material, price
                FROM catalog_kits
                WHERE model_code = %s
                ORDER BY material
                """,
                (code,),
            )
            model["kits"] = cur.fetchall()

            cur.execute(
                """
                SELECT url
                FROM catalog_images
                WHERE model_code = %s
                ORDER BY sort_order ASC, url ASC
                """,
                (code,),
            )
            model["images"] = [r["url"] for r in cur.fetchall()]

            return model


def upsert_model(code, name, short, price_drawings, drawings_url):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO catalog_models (code, name, short, price_drawings, drawings_url, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (code)
                DO UPDATE SET
                  name = EXCLUDED.name,
                  short = EXCLUDED.short,
                  price_drawings = EXCLUDED.price_drawings,
                  drawings_url = EXCLUDED.drawings_url,
                  updated_at = NOW()
                """,
                (code, name, short, int(price_drawings or 0), drawings_url),
            )
        conn.commit()


def replace_kits(model_code, kits):
    """
    kits: список dict {"material": str, "price": int}
    """
    kits = kits or []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_kits WHERE model_code = %s", (model_code,))
            for k in kits:
                cur.execute(
                    """
                    INSERT INTO catalog_kits (id, model_code, material, price)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (uuid.uuid4(), model_code, k["material"], int(k["price"])),
                )
        conn.commit()


def replace_images(model_code, urls):
    """
    urls: список URL (строки). Полностью перезаписывает фото.
    """
    urls = urls or []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_images WHERE model_code = %s", (model_code,))
            order_num = 0
            for url in urls:
                order_num += 1
                cur.execute(
                    """
                    INSERT INTO catalog_images (id, model_code, url, sort_order)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (uuid.uuid4(), model_code, url, order_num),
                )
        conn.commit()


def delete_model(code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_models WHERE code = %s", (code,))
        conn.commit()
