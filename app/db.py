import os
import uuid

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """
    Создаёт таблицы и безопасно добавляет новые колонки.
    Можно вызывать на старте сколько угодно раз.
    """
    create_sql = """
    CREATE TABLE IF NOT EXISTS leads (
      id UUID PRIMARY KEY,
      phone TEXT NOT NULL,
      source TEXT NOT NULL,
      model_code TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    migrate_sql = [
        # профиль
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS full_name TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS city TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS interest TEXT NOT NULL DEFAULT '';",

        # CRM
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS segment TEXT NOT NULL DEFAULT 'unknown';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS note TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMPTZ;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS remind_at TIMESTAMPTZ;",

        # индексы
        "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);",
        "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);",
        "CREATE INDEX IF NOT EXISTS idx_leads_segment ON leads(segment);",
        "CREATE INDEX IF NOT EXISTS idx_leads_remind_at ON leads(remind_at);",
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for stmt in migrate_sql:
                cur.execute(stmt)
        conn.commit()


# -------------------------
# Leads
# -------------------------
def insert_lead(phone: str, source: str, model_code: str | None = None):
    lead_id = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (id, phone, source, model_code)
                VALUES (%s, %s, %s, %s)
                """,
                (lead_id, phone, source, model_code),
            )
        conn.commit()
    return str(lead_id)


def count_leads() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM leads")
            row = cur.fetchone()
            return int(row["cnt"])


def list_leads(limit: int = 20, offset: int = 0):
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


def get_lead(lead_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, phone, source, model_code, created_at,
                       full_name, city, interest,
                       segment, status, note, last_contact_at, remind_at
                FROM leads
                WHERE id = %s
                """,
                (lead_id,),
            )
            return cur.fetchone()


def update_lead_profile(lead_id: str, full_name=None, city=None, interest=None):
    sets = []
    params = []

    if full_name is not None:
        sets.append("full_name = %s")
        params.append((full_name or "").strip())

    if city is not None:
        sets.append("city = %s")
        params.append((city or "").strip())

    if interest is not None:
        sets.append("interest = %s")
        params.append((interest or "").strip())

    if not sets:
        return

    sets.append("last_contact_at = NOW()")
    params.append(lead_id)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leads SET " + ", ".join(sets) + " WHERE id = %s",
                tuple(params),
            )
        conn.commit()


def set_lead_status(lead_id: str, status: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET status = %s, last_contact_at = NOW()
                WHERE id = %s
                """,
                (status, lead_id),
            )
        conn.commit()


def set_lead_segment(lead_id: str, segment: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET segment = %s, last_contact_at = NOW()
                WHERE id = %s
                """,
                (segment, lead_id),
            )
        conn.commit()


def append_lead_note(lead_id: str, note_text: str):
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


def set_lead_remind_at(lead_id: str, remind_at_iso_or_none):
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


def due_reminders(limit: int = 30):
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