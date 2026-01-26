 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/app/db.py b/app/db.py
index 003d23ca5218cf194be7ade1a75ca1393db596e2..b501559cf2c2e07dfd7c52d86cb4c08833581f53 100644
--- a/app/db.py
+++ b/app/db.py
@@ -47,50 +47,53 @@ def init_db():
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
+        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS full_name TEXT NOT NULL DEFAULT '';",
+        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS city TEXT NOT NULL DEFAULT '';",
+        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS interest TEXT NOT NULL DEFAULT '';",
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
@@ -120,51 +123,51 @@ def count_leads():
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
-                       name, segment, status, note, last_contact_at, remind_at
+                       name, full_name, city, interest, segment, status, note, last_contact_at, remind_at
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
@@ -205,50 +208,85 @@ def append_lead_note(lead_id, note_text):
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
 
 
+def update_lead_profile(lead_id, full_name=None, city=None, interest=None):
+    """
+    Обновляет поля профиля лида. Передавай только то, что меняешь.
+    """
+    sets = []
+    params = []
+
+    if full_name is not None:
+        sets.append("full_name = %s")
+        params.append((full_name or "").strip())
+
+    if city is not None:
+        sets.append("city = %s")
+        params.append((city or "").strip())
+
+    if interest is not None:
+        sets.append("interest = %s")
+        params.append((interest or "").strip())
+
+    if not sets:
+        return
+
+    sets.append("last_contact_at = NOW()")
+
+    params.append(lead_id)
+
+    with get_conn() as conn:
+        with conn.cursor() as cur:
+            cur.execute(
+                f"UPDATE leads SET {', '.join(sets)} WHERE id = %s",
+                tuple(params),
+            )
+        conn.commit()
+
+
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
 
EOF
)
