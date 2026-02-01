"""
Database layer for the catalog bot.

This module defines functions to initialize the database schema and perform
CRUD operations on clients, products, orders and payments. It uses the
psycopg library for PostgreSQL access. The connection string is read from
the DATABASE_URL environment variable.

Tables created:
    clients      — registered clients (Telegram users)
    products     — catalog items with code, name, price and unit
    orders       — orders placed by clients
    order_items  — items within each order
    payments     — payments against orders

Each function opens a new connection using get_conn(). For high throughput
applications you may consider using a connection pool.
"""

import os
import uuid
from typing import List, Dict, Any, Optional

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def get_conn():
    """Return a new psycopg connection using DATABASE_URL."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

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
        price NUMERIC(12,2) NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    create_orders_table = """
    CREATE TABLE IF NOT EXISTS orders (
        id UUID PRIMARY KEY,
        client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        status TEXT NOT NULL DEFAULT 'new',
        total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
        shipped_at TIMESTAMPTZ,
        delivered_at TIMESTAMPTZ,
        paid_at TIMESTAMPTZ
    );
    """

    create_order_items_table = """
    CREATE TABLE IF NOT EXISTS order_items (
        id UUID PRIMARY KEY,
        order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
        product_id UUID REFERENCES products(id) ON DELETE SET NULL,
        quantity NUMERIC(12,2) NOT NULL DEFAULT 0,
        price NUMERIC(12,2) NOT NULL DEFAULT 0,
        amount NUMERIC(12,2) NOT NULL DEFAULT 0
    );
    """

    create_payments_table = """
    CREATE TABLE IF NOT EXISTS payments (
        id UUID PRIMARY KEY,
        order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
        amount NUMERIC(12,2) NOT NULL,
        payment_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        method TEXT NOT NULL DEFAULT 'post'
    );
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(create_client_table)
            cur.execute(create_products_table)
            cur.execute(create_orders_table)
            cur.execute(create_order_items_table)
            cur.execute(create_payments_table)
        conn.commit()

def insert_client(tg_id: int, phone: str, name: str = "", address: str = "") -> str:
    """
    Create a new client record. If a client with tg_id already exists, return
    its ID without inserting a new row.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if tg_id:
                cur.execute("SELECT id FROM clients WHERE tg_id = %s", (tg_id,))
                row = cur.fetchone()
                if row:
                    return str(row["id"])
            cid = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO clients (id, tg_id, phone, name, address)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (cid, tg_id, phone, name, address),
            )
        conn.commit()
    return str(cid)

def get_client_by_tg_id(tg_id: int) -> Optional[Dict[str, Any]]:
    """Return client row for a given Telegram user ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM clients WHERE tg_id = %s", (tg_id,))
            return cur.fetchone()

def list_products(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Return a list of products ordered by name."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, name, unit, price, description
                FROM products
                ORDER BY name ASC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return cur.fetchall()

def get_product_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Return product row by its code."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, name, unit, price, description
                FROM products
                WHERE code = %s
                """,
                (code,),
            )
            return cur.fetchone()

def upsert_product(code: str, name: str, description: str = "", unit: str = "", price: float = 0.0) -> None:
    """
    Insert or update a product based on its code.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM products WHERE code = %s", (code,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE products
                    SET name = %s, description = %s, unit = %s, price = %s
                    WHERE code = %s
                    """,
                    (name, description, unit, price, code),
                )
            else:
                pid = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO products (id, code, name, description, unit, price)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (pid, code, name, description, unit, price),
                )
        conn.commit()

def create_order(client_id: str) -> str:
    """Create a new order for the given client and return its ID."""
    oid = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (id, client_id, status, total_amount)
                VALUES (%s, %s, 'new', 0)
                """,
                (oid, client_id),
            )
        conn.commit()
    return str(oid)

def add_order_item(order_id: str, product_id: str, quantity: float, price: float) -> None:
    """Add an item to an order."""
    amount = (quantity or 0) * (price or 0)
    iid = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO order_items (id, order_id, product_id, quantity, price, amount)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (iid, order_id, product_id, quantity, price, amount),
            )
        conn.commit()

def update_order_total(order_id: str) -> None:
    """Recalculate and update the total_amount for the given order."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM order_items WHERE order_id = %s",
                (order_id,),
            )
            row = cur.fetchone()
            total = row["total"] if row else 0
            cur.execute(
                "UPDATE orders SET total_amount = %s WHERE id = %s",
                (total, order_id),
            )
        conn.commit()

def list_orders(status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Return orders optionally filtered by status."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT o.id, o.created_at, o.status, o.total_amount,
                           c.phone AS phone, c.name AS name
                    FROM orders o
                    LEFT JOIN clients c ON o.client_id = c.id
                    WHERE o.status = %s
                    ORDER BY o.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (status, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT o.id, o.created_at, o.status, o.total_amount,
                           c.phone AS phone, c.name AS name
                    FROM orders o
                    LEFT JOIN clients c ON o.client_id = c.id
                    ORDER BY o.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
            return cur.fetchall()

def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Return an order and its items."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.client_id, o.created_at, o.status, o.total_amount,
                       o.shipped_at, o.delivered_at, o.paid_at,
                       c.phone AS client_phone, c.name AS client_name, c.address AS client_address
                FROM orders o
                LEFT JOIN clients c ON o.client_id = c.id
                WHERE o.id = %s
                """,
                (order_id,),
            )
            order = cur.fetchone()
            if not order:
                return None
            cur.execute(
                """
                SELECT oi.id, oi.product_id, oi.quantity, oi.price, oi.amount,
                       p.code AS product_code, p.name AS product_name, p.unit AS product_unit
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
                """,
                (order_id,),
            )
            items = cur.fetchall()
            order["items"] = items
            return order

def set_order_status(order_id: str, status: str) -> None:
    """Update the status of an order. Also sets timestamps for shipped/delivered/paid statuses."""
    fields = {"status": status}
    # set dates automatically depending on status
    if status == "shipped":
        fields["shipped_at"] = "NOW()"
    elif status == "delivered":
        fields["delivered_at"] = "NOW()"
    elif status == "paid":
        fields["paid_at"] = "NOW()"
    sets = []
    params = []
    for k, v in fields.items():
        if v == "NOW()":
            sets.append(f"{k} = NOW()")
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    params.append(order_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET " + ", ".join(sets) + " WHERE id = %s",
                tuple(params),
            )
        conn.commit()

def record_payment(order_id: str, amount: float, method: str = "post") -> None:
    """
    Insert a payment record and mark the order as paid.
    """
    pid = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payments (id, order_id, amount, method)
                VALUES (%s, %s, %s, %s)
                """,
                (pid, order_id, amount, method),
            )
            cur.execute(
                "UPDATE orders SET status = 'paid', paid_at = NOW() WHERE id = %s",
                (order_id,),
            )
        conn.commit()

def replace_products(items: List[Dict[str, Any]]) -> None:
    """
    Bulk upsert of product list. Each dict in `items` should have at least
    'code', 'name', and 'price'. Optional keys: 'unit', 'description'.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            for it in items:
                code = it.get("code")
                name = it.get("name")
                price = it.get("price")
                unit = it.get("unit", "")
                desc = it.get("description", "")
                if not code or not name:
                    continue
                cur.execute("SELECT id FROM products WHERE code = %s", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE products
                        SET name = %s, description = %s, unit = %s, price = %s
                        WHERE code = %s
                        """,
                        (name, desc, unit, price, code),
                    )
                else:
                    pid = uuid.uuid4()
                    cur.execute(
                        """
                        INSERT INTO products (id, code, name, description, unit, price)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (pid, code, name, desc, unit, price),
                    )
        conn.commit()

def list_orders_by_client(client_id: str) -> List[Dict[str, Any]]:
    """
    Return all orders for a particular client ID, newest first.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, status, total_amount, shipped_at, delivered_at, paid_at
                FROM orders
                WHERE client_id = %s
                ORDER BY created_at DESC
                """,
                (client_id,),
            )
            return cur.fetchall()

# New functions for clients listing and details

def list_clients_with_balance(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Return a list of clients with their unpaid balance. Balance is calculated as the
    sum of total_amount of all orders that are not marked as 'paid'. The result
    includes tg_id, phone, name, address and computed balance for each client.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.tg_id, c.phone, c.name, c.address,
                       COALESCE(SUM(CASE WHEN o.status != 'paid' THEN o.total_amount ELSE 0 END), 0) AS balance
                FROM clients c
                LEFT JOIN orders o ON c.id = o.client_id
                GROUP BY c.id, c.tg_id, c.phone, c.name, c.address
                ORDER BY c.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return cur.fetchall()

def get_client_with_orders(client_id: str) -> Optional[Dict[str, Any]]:
    """
    Return a client with their details and list of orders. The returned dict includes
    phone, name, address, and a list of orders (each with id, created_at, status,
    total_amount). It also includes a computed 'balance' field summing unpaid orders.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tg_id, phone, name, address
                FROM clients
                WHERE id = %s
                """,
                (client_id,),
            )
            client = cur.fetchone()
            if not client:
                return None
            cur.execute(
                """
                SELECT id, created_at, status, total_amount, shipped_at, delivered_at, paid_at
                FROM orders
                WHERE client_id = %s
                ORDER BY created_at DESC
                """,
                (client_id,),
            )
            orders = cur.fetchall()
            client["orders"] = orders
            # compute unpaid balance
            balance = 0
            for o in orders:
                if o.get("status") != "paid":
                    amt = o.get("total_amount") or 0
                    try:
                        balance += float(amt)
                    except Exception:
                        balance += 0
            client["balance"] = balance
            return client
