 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/shop_db.py b/shop_db.py
index d3718a8397c96d936bd90bd1a4b7d8e6f8bb5658..816d25a6d2f368911ad79387835ecdb979852117 100644
--- a/shop_db.py
+++ b/shop_db.py
@@ -23,50 +23,56 @@ from typing import List, Dict, Any, Optional
 
 import psycopg
 from psycopg.rows import dict_row
 
 DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
 
 def get_conn():
     """Return a new psycopg connection using DATABASE_URL."""
     if not DATABASE_URL:
         raise RuntimeError("DATABASE_URL is not set")
     return psycopg.connect(DATABASE_URL, row_factory=dict_row)
 
 def cleanup_legacy_tables():
     """
     Удаляет старые таблицы от предыдущих ботов, если они существуют
     """
     legacy_sql = """
     DROP TABLE IF EXISTS
         leads,
         lead_notes,
         models,
         models_data,
         sessions,
         users,
         orders_old
+    ;
+    """
+    with get_conn() as conn:
+        with conn.cursor() as cur:
+            cur.execute(legacy_sql)
+        conn.commit()
 
 
 def init_db():
     """
     Create tables if they do not exist. This function is idempotent and
     can be called multiple times on startup.
     """
     create_client_table = """
     CREATE TABLE IF NOT EXISTS clients (
         id UUID PRIMARY KEY,
         tg_id BIGINT UNIQUE,
         phone TEXT NOT NULL,
         name TEXT NOT NULL DEFAULT '',
         address TEXT NOT NULL DEFAULT '',
         created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
     );
     """
 
     create_products_table = """
     CREATE TABLE IF NOT EXISTS products (
         id UUID PRIMARY KEY,
         code TEXT UNIQUE NOT NULL,
         name TEXT NOT NULL,
         description TEXT NOT NULL DEFAULT '',
         unit TEXT NOT NULL DEFAULT '',
 
EOF
)