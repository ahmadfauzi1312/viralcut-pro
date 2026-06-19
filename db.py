import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "viralcut.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn):
    c = conn.cursor()
    # queue column migrations
    existing_queue = {row[1] for row in c.execute("PRAGMA table_info(queue)").fetchall()}
    queue_migrations = [
        ("sort_order",    "ALTER TABLE queue ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"),
        ("assigned_slot", "ALTER TABLE queue ADD COLUMN assigned_slot INTEGER REFERENCES schedule(id)"),
        ("notes",         "ALTER TABLE queue ADD COLUMN notes TEXT NOT NULL DEFAULT ''"),
    ]
    for col, sql in queue_migrations:
        if col not in existing_queue:
            c.execute(sql)
    conn.commit()


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            username TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_time TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            channel TEXT NOT NULL,
            thumbnail TEXT NOT NULL,
            views TEXT NOT NULL,
            likes TEXT NOT NULL,
            genre TEXT NOT NULL,
            score INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            assigned_slot INTEGER REFERENCES schedule(id),
            notes TEXT NOT NULL DEFAULT '',
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_date TEXT NOT NULL,
            schedule_time TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'All',
            video_id TEXT DEFAULT NULL,
            clip_title TEXT DEFAULT NULL,
            caption TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS captions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            genre TEXT NOT NULL,
            short_cap TEXT NOT NULL,
            medium_cap TEXT NOT NULL,
            long_cap TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    _migrate(conn)

    c.execute("SELECT COUNT(*) FROM accounts")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO accounts (platform, username, enabled) VALUES (?, ?, ?)", [
            ("TikTok",    "@viralcutpro", 1),
            ("Instagram", "@viralcutpro", 1),
            ("YouTube",   "ViralCut Pro", 0),
        ])

    c.execute("SELECT COUNT(*) FROM schedule")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO schedule (slot_time, enabled) VALUES (?, ?)", [
            ("12:00", 1),
            ("16:00", 1),
            ("20:00", 1),
        ])

    defaults = [
        ("genres",          "Automotive,Food,DIY,Tech,Lifestyle"),
        ("clip_duration",   "60"),
        ("viral_score_min", "60"),
        ("clips_per_day",   "3"),
    ]
    for key, value in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()
    conn.close()
