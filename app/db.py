import os
import uuid
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL)

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS leads (
      id UUID PRIMARY KEY,
      phone TEXT NOT NULL,
      source TEXT NOT NULL,
      model_code TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
    CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

def insert_lead(phone: str, source: str, model_code: str | None):
    lead_id = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO leads (id, phone, source, model_code) VALUES (%s, %s, %s, %s)",
                (lead_id, phone, source, model_code),
            )
        conn.commit()
    return str(lead_id)
