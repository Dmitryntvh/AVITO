import os
import uuid
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS leads (
      id UUID PRIMARY KEY,
      phone TEXT NOT NULL,
      source TEXT NOT NULL,
      model_code TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS catalog_models (
      code TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      short TEXT NOT NULL DEFAULT '',
      price_drawings INTEGER NOT NULL DEFAULT 0,
      drawings_url TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS catalog_kits (
      id UUID PRIMARY KEY,
      model_code TEXT NOT NULL REFERENCES catalog_models(code) ON DELETE CASCADE,
      material TEXT NOT NULL,
      price INTEGER NOT NULL DEFAULT 0
    );

    -- фото (URL) для модели
    CREATE TABLE IF NOT EXISTS catalog_images (
      id UUID PRIMARY KEY,
      model_code TEXT NOT NULL REFERENCES catalog_models(code) ON DELETE CASCADE,
      url TEXT NOT NULL,
      sort_order INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_catalog_kits_model ON catalog_kits(model_code);
    CREATE INDEX IF NOT EXISTS idx_catalog_images_model ON catalog_images(model_code);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def insert_lead(phone, source, model_code):
    lead_id = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO leads (id, phone, source, model_code) VALUES (%s, %s, %s, %s)",
                (lead_id, phone, source, model_code),
            )
        conn.commit()
    return str(lead_id)


def list_models():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, name, short, price_drawings, drawings_url, updated_at "
                "FROM catalog_models ORDER BY updated_at DESC"
            )
            return cur.fetchall()


def get_model(code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, name, short, price_drawings, drawings_url "
                "FROM catalog_models WHERE code = %s",
                (code,),
            )
            model = cur.fetchone()
            if not model:
                return None

            cur.execute(
                "SELECT material, price FROM catalog_kits WHERE model_code = %s ORDER BY material",
                (code,),
            )
            model["kits"] = cur.fetchall()

            cur.execute(
                "SELECT url FROM catalog_images WHERE model_code = %s ORDER BY sort_order ASC, url ASC",
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
                (code, name, short, price_drawings, drawings_url),
            )
        conn.commit()


def replace_kits(model_code, kits):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_kits WHERE model_code = %s", (model_code,))
            for kit in kits:
                cur.execute(
                    "INSERT INTO catalog_kits (id, model_code, material, price) VALUES (%s, %s, %s, %s)",
                    (uuid.uuid4(), model_code, kit["material"], kit["price"]),
                )
        conn.commit()


def replace_images(model_code, urls):
    """
    urls: список строк URL. Полностью перезаписывает фото модели.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_images WHERE model_code = %s", (model_code,))
            order_num = 0
            for url in urls:
                order_num += 1
                cur.execute(
                    "INSERT INTO catalog_images (id, model_code, url, sort_order) VALUES (%s, %s, %s, %s)",
                    (uuid.uuid4(), model_code, url, order_num),
                )
        conn.commit()


def delete_model(code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_models WHERE code = %s", (code,))
        conn.commit()
