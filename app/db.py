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
    -- лиды
    CREATE TABLE IF NOT EXISTS leads (
      id UUID PRIMARY KEY,
      phone TEXT NOT NULL,
      source TEXT NOT NULL,
      model_code TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
    CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);

    -- каталог: модели
    CREATE TABLE IF NOT EXISTS catalog_models (
      code TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      short TEXT NOT NULL DEFAULT '',
      price_drawings INTEGER NOT NULL DEFAULT 0,
      drawings_url TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- каталог: комплекты (заготовки)
    CREATE TABLE IF NOT EXISTS catalog_kits (
      id UUID PRIMARY KEY,
      model_code TEXT NOT NULL REFERENCES catalog_models(code) ON DELETE CASCADE,
      material TEXT NOT NULL,
      price INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_catalog_kits_model ON catalog_kits(model_code);
    """
    with get_conn() as conn:
        with
