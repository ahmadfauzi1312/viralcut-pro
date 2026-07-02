import os
import re
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    try:
        import psycopg2
        import psycopg2.extras
        USE_POSTGRES = True
    except ImportError:
        USE_POSTGRES = False
else:
    USE_POSTGRES = False


def get_pg_conn():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


def get_sqlite_conn():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viralcut.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# Map of table_name -> primary/unique key column(s) for ON CONFLICT clause
TABLE_CONFLICT_KEYS = {
    "settings": "key",
    "captions": "video_id",
}


def _translate_sql(sql: str) -> str:
    """
    Translate SQLite-specific SQL to PostgreSQL-compatible SQL.
    Handles: ? -> %s, INSERT OR REPLACE -> INSERT ... ON CONFLICT DO UPDATE,
             AUTOINCREMENT -> SERIAL (not needed at runtime, only DDL)
    """
    original = sql

    # Handle INSERT OR REPLACE INTO table_name (...)
    m = re.match(
        r'\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)',
        sql, re.IGNORECASE
    )
    if m:
        table = m.group(1)
        columns_raw = [c.strip() for c in m.group(2).split(",")]
        placeholders = [p.strip() for p in m.group(3).split(",")]

        conflict_key = TABLE_CONFLICT_KEYS.get(table, columns_raw[0])

        # Build the new query
        update_clauses = []
        for col in columns_raw:
            if col != conflict_key:
                update_clauses.append(f"{col} = EXCLUDED.{col}")

        new_sql = (
            f"INSERT INTO {table} ({', '.join(columns_raw)}) "
            f"VALUES ({', '.join(placeholders)}) "
            f"ON CONFLICT ({conflict_key}) DO UPDATE SET "
            f"{', '.join(update_clauses) if update_clauses else f'{conflict_key} = EXCLUDED.{conflict_key}'}"
        )
        sql = new_sql

    # Convert ? placeholders to %s (but only outside of already-converted parts)
    sql = sql.replace("?", "%s")

    return sql


class UnifiedConn:
    def __init__(self):
        if USE_POSTGRES:
            self._conn = get_pg_conn()
            self._pg = True
        else:
            self._conn = get_sqlite_conn()
            self._pg = False

    def execute(self, sql, params=()):
        if self._pg:
            sql = _translate_sql(sql)
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
        except Exception as e:
            # Rollback on error to keep connection usable
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise e
        return UnifiedCursor(cur, self._pg)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class UnifiedCursor:
    def __init__(self, cur, is_pg):
        self._cur = cur
        self._pg = is_pg

    def fetchall(self):
        rows = self._cur.fetchall()
        if self._pg:
            return [dict(r) for r in rows]
        return rows

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if self._pg:
            return dict(row)
        return row

    @property
    def lastrowid(self):
        if self._pg:
            try:
                self._cur.execute("SELECT lastval()")
                return self._cur.fetchone()["lastval"]
            except Exception:
                return None
        return self._cur.lastrowid


def get_db():
    return UnifiedConn()


def init_db():
    conn = get_db()
    if USE_POSTGRES:
        _init_postgres(conn)
    else:
        _init_sqlite(conn)
    conn.commit()
    conn.close()


def _init_sqlite(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        username TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_time TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL,
        title TEXT,
        channel TEXT,
        thumbnail TEXT,
        views TEXT,
        likes TEXT,
        genre TEXT,
        score INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 60,
        status TEXT DEFAULT 'pending',
        notes TEXT,
        sort_order INTEGER DEFAULT 0,
        assigned_slot INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS captions (
        video_id TEXT PRIMARY KEY,
        title TEXT,
        genre TEXT,
        short_cap TEXT,
        medium_cap TEXT,
        long_cap TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_date TEXT NOT NULL,
        schedule_time TEXT NOT NULL,
        platform TEXT DEFAULT 'All',
        video_id TEXT,
        clip_title TEXT,
        caption TEXT,
        status TEXT DEFAULT 'scheduled',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    existing = conn.execute("SELECT COUNT(*) as c FROM schedule").fetchone()
    c = existing['c'] if isinstance(existing, dict) else existing[0]
    if c == 0:
        for t in ["12:00", "16:00", "20:00"]:
            conn.execute("INSERT INTO schedule (slot_time, enabled) VALUES (?, 1)", (t,))


def _init_postgres(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        platform TEXT NOT NULL,
        username TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS schedule (
        id SERIAL PRIMARY KEY,
        slot_time TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS queue (
        id SERIAL PRIMARY KEY,
        video_id TEXT NOT NULL,
        title TEXT,
        channel TEXT,
        thumbnail TEXT,
        views TEXT,
        likes TEXT,
        genre TEXT,
        score INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 60,
        status TEXT DEFAULT 'pending',
        notes TEXT,
        sort_order INTEGER DEFAULT 0,
        assigned_slot INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS captions (
        video_id TEXT PRIMARY KEY,
        title TEXT,
        genre TEXT,
        short_cap TEXT,
        medium_cap TEXT,
        long_cap TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
        id SERIAL PRIMARY KEY,
        schedule_date TEXT NOT NULL,
        schedule_time TEXT NOT NULL,
        platform TEXT DEFAULT 'All',
        video_id TEXT,
        clip_title TEXT,
        caption TEXT,
        status TEXT DEFAULT 'scheduled',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    existing = conn.execute("SELECT COUNT(*) as c FROM schedule").fetchone()
    c = existing['c'] if isinstance(existing, dict) else existing[0]
    if c == 0:
        for t in ["12:00", "16:00", "20:00"]:
            conn.execute("INSERT INTO schedule (slot_time, enabled) VALUES (%s, 1)", (t,))


def migrate_db():
    """Add any missing columns introduced after initial schema creation."""
    conn = get_db()
    new_cols = [
        ("start_sec",   "REAL DEFAULT 0"),
        ("end_sec",     "REAL DEFAULT 0"),
        ("source_url",  "TEXT DEFAULT ''"),
    ]
    if USE_POSTGRES:
        for col, defn in new_cols:
            try:
                conn.execute(f"ALTER TABLE queue ADD COLUMN IF NOT EXISTS {col} {defn}")
            except Exception:
                pass
    else:
        for col, defn in new_cols:
            try:
                conn.execute(f"ALTER TABLE queue ADD COLUMN {col} {defn}")
            except Exception:
                pass  # Column already exists
    conn.commit()
    conn.close()
