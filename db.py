import os
import sqlite3

# Try to use PostgreSQL if DATABASE_URL is available, otherwise fall back to SQLite
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


# ── PostgreSQL connection ────────────────────────────────────────────────────

def get_pg_conn():
    url = DATABASE_URL
    # Railway uses postgres:// but psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


# ── SQLite connection (fallback) ─────────────────────────────────────────────

def get_sqlite_conn():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viralcut.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Unified connection wrapper ───────────────────────────────────────────────

class UnifiedConn:
    """Wraps psycopg2 or sqlite3 connection with a unified interface."""

    def __init__(self):
        if USE_POSTGRES:
            self._conn = get_pg_conn()
            self._pg = True
        else:
            self._conn = get_sqlite_conn()
            self._pg = False

    def execute(self, sql, params=()):
        # Convert SQLite ? placeholders to PostgreSQL %s
        if self._pg:
            sql = sql.replace("?", "%s")
            # Convert INSERT OR REPLACE to INSERT ... ON CONFLICT DO UPDATE
            if sql.strip().upper().startswith("INSERT OR REPLACE"):
                sql = sql.replace("INSERT OR REPLACE", "INSERT", 1)
                # We'll handle conflicts per-table below via upsert helper
        cur = self._conn.cursor()
        cur.execute(sql, params)
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
    """Wraps cursor to provide fetchall/fetchone that return dict-like rows."""

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
                return self._cur.fetchone()[0]
            except Exception:
                return None
        return self._cur.lastrowid


def get_db():
    return UnifiedConn()


# ── Schema ───────────────────────────────────────────────────────────────────

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
    # Seed default schedule slots
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
    # Upsert for settings needs special handling in postgres
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    # Seed default schedule slots if empty
    existing = conn.execute("SELECT COUNT(*) as c FROM schedule").fetchone()
    c = existing['c'] if isinstance(existing, dict) else existing[0]
    if c == 0:
        for t in ["12:00", "16:00", "20:00"]:
            conn.execute("INSERT INTO schedule (slot_time, enabled) VALUES (%s, 1)", (t,))
