import os
import uuid
import secrets as _secrets
import requests as req_lib
from datetime import date, timedelta, datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from db import init_db, get_db
from youtube import fetch_trending, fetch_all_sources
from youtube_upload import get_valid_access_token, upload_video_to_youtube, get_channel_info
from analyzer import analyze_links
from captions import generate as gen_captions
from video_processor import process_full_pipeline, CLIPS_DIR, check_ffmpeg, check_ytdlp
from scheduler import start_scheduler
from clip_processor import (
    process_clip as ffmpeg_process,
    get_video_info,
    UPLOAD_DIR,
    PROCESSED_DIR,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "viralcut-dev-secret")

init_db()
start_scheduler(app)

MOCK_VIDEOS = [
    {"video_id": "mock1",  "title": "I Bought a $500 Car and Fixed It in a Weekend",    "channel": "GarageKings",   "thumbnail": "", "views": "4.2M", "views_raw": 4200000,  "likes": "180K", "published": "2025-06-10", "genre": "Automotive", "score": 94, "duration": 30},
    {"video_id": "mock2",  "title": "This $20 Tool Changed Everything About My Kitchen", "channel": "KitchenHacks",  "thumbnail": "", "views": "3.8M", "views_raw": 3800000,  "likes": "142K", "published": "2025-06-12", "genre": "Food",       "score": 91, "duration": 30},
    {"video_id": "mock3",  "title": "Building a Full Deck in 48 Hours — Time Lapse",    "channel": "BackyardBuilds","thumbnail": "", "views": "6.1M", "views_raw": 6100000,  "likes": "210K", "published": "2025-06-08", "genre": "DIY",        "score": 89, "duration": 60},
    {"video_id": "mock4",  "title": "The iPhone Feature Nobody Talks About",             "channel": "TechWithTom",   "thumbnail": "", "views": "7.5M", "views_raw": 7500000,  "likes": "390K", "published": "2025-06-14", "genre": "Tech",       "score": 97, "duration": 30},
    {"video_id": "mock5",  "title": "Morning Routine of a $10M CEO",                    "channel": "LifeOptimized", "thumbnail": "", "views": "5.3M", "views_raw": 5300000,  "likes": "175K", "published": "2025-06-11", "genre": "Lifestyle",  "score": 88, "duration": 60},
    {"video_id": "mock6",  "title": "Fixing a Ferrari with Zip Ties (It Worked)",       "channel": "WrenchTime",    "thumbnail": "", "views": "9.2M", "views_raw": 9200000,  "likes": "510K", "published": "2025-06-09", "genre": "Automotive", "score": 96, "duration": 30},
    {"video_id": "mock7",  "title": "One Pan Pasta That Actually Tastes Good",           "channel": "QuickBites",    "thumbnail": "", "views": "2.9M", "views_raw": 2900000,  "likes": "88K",  "published": "2025-06-13", "genre": "Food",       "score": 82, "duration": 60},
    {"video_id": "mock8",  "title": "ChatGPT Prompt That Makes You 10x Productive",     "channel": "AIWorkflow",    "thumbnail": "", "views": "11.4M","views_raw": 11400000, "likes": "620K", "published": "2025-06-07", "genre": "Tech",       "score": 99, "duration": 30},
    {"video_id": "mock9",  "title": "How I Saved $50k in 12 Months on a Normal Salary", "channel": "MoneyMoves",    "thumbnail": "", "views": "8.8M", "views_raw": 8800000,  "likes": "430K", "published": "2025-06-10", "genre": "Lifestyle",  "score": 93, "duration": 30},
    {"video_id": "mock10", "title": "Building a Hidden Room Behind a Bookshelf",         "channel": "SecretSpaces",  "thumbnail": "", "views": "15.6M","views_raw": 15600000, "likes": "820K", "published": "2025-06-06", "genre": "DIY",        "score": 99, "duration": 30},
    {"video_id": "mock11", "title": "Turbocharging a Lawnmower (0-60 in 3s)",           "channel": "ChaosGarage",   "thumbnail": "", "views": "13.1M","views_raw": 13100000, "likes": "710K", "published": "2025-06-08", "genre": "Automotive", "score": 98, "duration": 30},
    {"video_id": "mock12", "title": "Street Food I Found at 2AM in Tokyo",               "channel": "NightBites",    "thumbnail": "", "views": "3.5M", "views_raw": 3500000,  "likes": "95K",  "published": "2025-06-12", "genre": "Food",       "score": 78, "duration": 60},
]


def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def get_api_key():
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        return key
    settings = get_settings()
    return settings.get("youtube_api_key", "").strip()


def filter_videos(videos, min_score, genres):
    genre_list = [g.strip() for g in genres.split(",") if g.strip()]
    return [v for v in videos if v["score"] >= min_score and (not genre_list or v["genre"] in genre_list)]


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    conn = get_db()
    active_accounts = conn.execute("SELECT COUNT(*) as c FROM accounts WHERE enabled=1").fetchone()["c"]
    schedule = conn.execute("SELECT * FROM schedule ORDER BY id").fetchall()
    queue_count = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='pending'").fetchone()["c"]
    conn.close()
    next_slot = next((s["slot_time"] for s in schedule if s["enabled"]), None)
    return render_template("dashboard.html", active="dashboard",
                           active_accounts=active_accounts,
                           schedule=schedule,
                           next_slot=next_slot,
                           queue_count=queue_count)


@app.route("/viral-finder")
def viral_finder():
    api_key = get_api_key()
    settings = get_settings()
    min_score = int(settings.get("viral_score_min", 45))
    genres = settings.get("genres", "Automotive,Food,DIY,Tech,Lifestyle")

    conn = get_db()
    queued_ids = {r["video_id"] for r in conn.execute("SELECT video_id FROM queue").fetchall()}
    capped_ids = {r["video_id"] for r in conn.execute("SELECT video_id FROM captions").fetchall()}
    conn.close()

    error = None
    scanned = False
    if api_key:
        try:
            raw = fetch_all_sources(api_key, region="ID", min_score=min_score)
            videos = raw
            scanned = True
        except Exception:
            videos = filter_videos(MOCK_VIDEOS, min_score, genres)
    else:
        videos = filter_videos(MOCK_VIDEOS, min_score, genres)

    for v in videos:
        v["in_queue"] = v["video_id"] in queued_ids
        v["has_captions"] = v["video_id"] in capped_ids

    return render_template("viral_finder.html", active="viral-finder",
                           videos=videos, scanned=scanned, error=error,
                           api_configured=bool(api_key),
                           min_score=min_score, genres=genres)


@app.route("/viral-finder/scan", methods=["POST"])
def viral_scan():
    api_key = get_api_key()
    settings = get_settings()
    min_score = int(settings.get("viral_score_min", 45))
    genres = settings.get("genres", "Automotive,Food,DIY,Tech,Lifestyle")

    conn = get_db()
    queued_ids = {r["video_id"] for r in conn.execute("SELECT video_id FROM queue").fetchall()}
    capped_ids = {r["video_id"] for r in conn.execute("SELECT video_id FROM captions").fetchall()}
    conn.close()

    error = None
    videos = []
    scanned = False

    if not api_key:
        error = "no_key"
        videos = filter_videos(MOCK_VIDEOS, min_score, genres)
    else:
        try:
            raw = fetch_all_sources(api_key, region="ID", min_score=min_score)
            videos = raw
            scanned = True
        except req_lib.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            error = "bad_key" if status == 400 else ("quota" if status == 403 else f"http_{status}")
            videos = filter_videos(MOCK_VIDEOS, min_score, genres)
        except req_lib.exceptions.ConnectionError:
            error = "network"
            videos = filter_videos(MOCK_VIDEOS, min_score, genres)
        except Exception as e:
            error = str(e)
            videos = filter_videos(MOCK_VIDEOS, min_score, genres)

    for v in videos:
        v["in_queue"] = v["video_id"] in queued_ids
        v["has_captions"] = v["video_id"] in capped_ids

    return render_template("viral_finder.html", active="viral-finder",
                           videos=videos, scanned=scanned, error=error,
                           api_configured=bool(api_key),
                           min_score=min_score, genres=genres)


@app.route("/captions/generate", methods=["POST"])
def captions_generate():
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "").strip()
    title = data.get("title", "").strip()
    channel = data.get("channel", "Unnamed").strip()
    genre = data.get("genre", "Lifestyle").strip()
    score = int(data.get("score", 70))

    if not video_id or not title:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    caps = gen_captions(title, genre, channel, score)

    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO captions (video_id, title, genre, short_cap, medium_cap, long_cap) VALUES (?,?,?,?,?,?)",
        (video_id, title, genre, caps["short"], caps["medium"], caps["long"])
    )
    conn.commit()
    conn.close()

    return jsonify({"ok": True, **caps})


@app.route("/captions/<video_id>")
def captions_get(video_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM captions WHERE video_id=?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "short": row["short_cap"], "medium": row["medium_cap"], "long": row["long_cap"]})


@app.route("/queue/add", methods=["POST"])
def queue_add():
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "").strip()
    title = data.get("title", "").strip()
    channel = data.get("channel", "").strip()
    thumbnail = data.get("thumbnail", "").strip()
    views = data.get("views", "").strip()
    likes = data.get("likes", "").strip()
    genre = data.get("genre", "").strip()
    score = int(data.get("score", 0))
    duration = int(data.get("duration", 60))

    if not video_id or not title:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    conn = get_db()
    if conn.execute("SELECT id FROM queue WHERE video_id=?", (video_id,)).fetchone():
        conn.close()
        return jsonify({"ok": False, "error": "already_queued"}), 409

    conn.execute(
        "INSERT INTO queue (video_id, title, channel, thumbnail, views, likes, genre, score, duration) VALUES (?,?,?,?,?,?,?,?,?)",
        (video_id, title, channel, thumbnail, views, likes, genre, score, duration)
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='pending'").fetchone()["c"]
    conn.close()
    return jsonify({"ok": True, "queue_count": count})


@app.route("/clip-editor")
def clip_editor():
    conn = get_db()
    queue = conn.execute("SELECT * FROM queue WHERE status='pending' ORDER BY sort_order ASC, added_at ASC").fetchall()
    conn.close()
    import json
    queue_json = json.dumps([dict(q) for q in queue])
    return render_template("clip_editor.html", active="clip-editor", queue=queue, queue_json=queue_json)


ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


@app.route("/clip/upload", methods=["POST"])
def clip_upload():
    f = request.files.get("video")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file received"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return jsonify({"ok": False, "error": f"Unsupported file type: {ext}"}), 400
    file_id = f"{uuid.uuid4().hex}{ext}"
    f.save(os.path.join(UPLOAD_DIR, file_id))
    info = get_video_info(file_id)
    return jsonify({"ok": True, "file_id": file_id, **info})


@app.route("/clip/preview/<path:file_id>")
def clip_preview(file_id):
    filename = os.path.basename(file_id)
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, conditional=True)


@app.route("/clip/process", methods=["POST"])
def clip_process():
    data = request.get_json(silent=True) or {}
    file_id = data.get("file_id", "").strip()
    start_sec = float(data.get("start") or 0)
    end_raw = data.get("end")
    end_sec = float(end_raw) if end_raw else None
    fmt = data.get("format", "portrait")
    quality = data.get("quality", "1080p")
    file_fmt = (data.get("file_format") or "mp4").lower().lstrip(".")

    if not file_id:
        return jsonify({"ok": False, "error": "file_id is required"}), 400

    out_name, err = ffmpeg_process(file_id, start_sec, end_sec, fmt, quality, file_fmt)
    if err:
        return jsonify({"ok": False, "error": err}), 500

    return jsonify({"ok": True, "download_url": f"/clip/download/{out_name}", "filename": out_name})


@app.route("/clip/download/<path:filename>")
def clip_download(filename):
    safe = os.path.basename(filename)
    path = os.path.join(PROCESSED_DIR, safe)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True, download_name=safe)


OAUTH_PLATFORMS = {
    "tiktok": {
        "label": "TikTok",
        "cred_fields": [("client_key", "Client Key"), ("client_secret", "Client Secret")],
        "auth_url": "https://www.tiktok.com/v2/auth/authorize?client_key={client_key}&scope=video.upload,user.info.basic&response_type=code&redirect_uri={redirect_uri}&state={state}",
    },
    "instagram": {
        "label": "Instagram",
        "cred_fields": [("app_id", "App ID"), ("app_secret", "App Secret")],
        "auth_url": "https://api.instagram.com/oauth/authorize?client_id={app_id}&redirect_uri={redirect_uri}&scope=instagram_basic,instagram_content_publish&response_type=code",
    },
    "youtube": {
        "label": "YouTube",
        "cred_fields": [("client_id", "Client ID"), ("client_secret", "Client Secret")],
        "auth_url": "https://accounts.google.com/o/oauth2/auth?client_id={client_id}&redirect_uri={redirect_uri}&scope=https://www.googleapis.com/auth/youtube.upload&response_type=code&access_type=offline",
    },
    "facebook": {
    "label": "Facebook",
    "cred_fields": [("app_id", "App ID"), ("app_secret", "App Secret")],
    "auth_url": "https://www.facebook.com/v18.0/dialog/oauth?client_id={app_id}&redirect_uri={redirect_uri}&scope=pages_manage_posts,pages_read_engagement,publish_video&response_type=code",
    },
}


@app.route("/oauth/save-creds/<platform>", methods=["POST"])
def oauth_save_creds(platform):
    if platform not in OAUTH_PLATFORMS:
        return redirect(url_for("accounts"))
    conn = get_db()
    cfg = OAUTH_PLATFORMS[platform]
    for field, _ in cfg["cred_fields"]:
        val = request.form.get(field, "").strip()
        if val:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (f"oauth_{platform}_{field}", val),
            )
    conn.commit()
    conn.close()
    flash(f"{cfg['label']} credentials saved.", "success")
    return redirect(url_for("accounts"))


@app.route("/oauth/connect/<platform>")
def oauth_connect(platform):
    if platform not in OAUTH_PLATFORMS:
        return redirect(url_for("accounts"))
    cfg = OAUTH_PLATFORMS[platform]
    settings = get_settings()
    creds = {f: settings.get(f"oauth_{platform}_{f}", "") for f, _ in cfg["cred_fields"]}
    if not all(creds.values()):
        flash(f"Save {cfg['label']} API credentials first.", "error")
        return redirect(url_for("accounts"))
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", os.environ.get("REPLIT_DOMAINS", "localhost:8000")).split(",")[0].strip()
    redirect_uri = f"https://{domain}/oauth/callback/{platform}"
    state = _secrets.token_urlsafe(16)
    auth_url = cfg["auth_url"].format(redirect_uri=redirect_uri, state=state, **creds)
    return redirect(auth_url)


@app.route("/oauth/callback/<platform>")
def oauth_callback(platform):
    code = request.args.get("code", "")
    error = request.args.get("error", "")
    if error or not code:
        flash(f"OAuth cancelled or failed: {error or 'no code received'}", "error")
        return redirect(url_for("accounts"))
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (f"oauth_{platform}_access_token", f"code:{code}"),
    )
    conn.commit()
    conn.close()
    flash(f"{platform.title()} connected!", "success")
    return redirect(url_for("accounts"))


@app.route("/oauth/disconnect/<platform>", methods=["POST"])
def oauth_disconnect(platform):
    conn = get_db()
    conn.execute("DELETE FROM settings WHERE key LIKE ?", (f"oauth_{platform}_%",))
    conn.commit()
    conn.close()
    flash(f"Disconnected {platform.title()}.", "success")
    return redirect(url_for("accounts"))


@app.route("/auto-upload")
def auto_upload():
    conn = get_db()
    queue = conn.execute("SELECT * FROM queue ORDER BY sort_order ASC, added_at ASC").fetchall()
    slots = conn.execute("SELECT * FROM schedule ORDER BY id").fetchall()
    connected_accounts = conn.execute("SELECT * FROM accounts WHERE enabled=1").fetchall()
    pending_count = sum(1 for r in queue if r["status"] == "pending")
    posted_count = sum(1 for r in queue if r["status"] == "posted")
    conn.close()
    settings = get_settings()
    yt_connected = bool(settings.get("oauth_youtube_access_token", ""))
    return render_template("auto_upload.html", active="auto-upload",
                           queue=queue, slots=slots,
                           connected_accounts=connected_accounts,
                           pending_count=pending_count,
                           posted_count=posted_count,
                           yt_connected=yt_connected)


@app.route("/queue/remove/<int:item_id>", methods=["POST"])
def queue_remove(item_id):
    conn = get_db()
    conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    flash("Removed from queue.", "success")
    return redirect(url_for("auto_upload"))


@app.route("/queue/reorder", methods=["POST"])
def queue_reorder():
    ids = (request.get_json(silent=True) or {}).get("ids", [])
    conn = get_db()
    for i, item_id in enumerate(ids):
        conn.execute("UPDATE queue SET sort_order=? WHERE id=?", (i, item_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/queue/assign-slot/<int:item_id>", methods=["POST"])
def queue_assign_slot(item_id):
    slot_id = (request.get_json(silent=True) or {}).get("slot_id") or None
    conn = get_db()
    conn.execute("UPDATE queue SET assigned_slot=? WHERE id=?", (slot_id, item_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/queue/mark-posted/<int:item_id>", methods=["POST"])
def queue_mark_posted(item_id):
    conn = get_db()
    conn.execute("UPDATE queue SET status='posted' WHERE id=?", (item_id,))
    conn.commit()
    pending = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='pending'").fetchone()["c"]
    posted = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='posted'").fetchone()["c"]
    conn.close()
    return jsonify({"ok": True, "pending_count": pending, "posted_count": posted})


@app.route("/queue/mark-pending/<int:item_id>", methods=["POST"])
def queue_mark_pending(item_id):
    conn = get_db()
    conn.execute("UPDATE queue SET status='pending' WHERE id=?", (item_id,))
    conn.commit()
    pending = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='pending'").fetchone()["c"]
    posted = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='posted'").fetchone()["c"]
    conn.close()
    return jsonify({"ok": True, "pending_count": pending, "posted_count": posted})


@app.route("/queue/clear-posted", methods=["POST"])
def queue_clear_posted():
    conn = get_db()
    conn.execute("DELETE FROM queue WHERE status='posted'")
    conn.commit()
    conn.close()
    flash("Posted videos cleared.", "success")
    return redirect(url_for("auto_upload"))


@app.route("/queue/update-notes/<int:item_id>", methods=["POST"])
def queue_update_notes(item_id):
    notes = (request.get_json(silent=True) or {}).get("notes", "")
    conn = get_db()
    conn.execute("UPDATE queue SET notes=? WHERE id=?", (notes.strip(), item_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/accounts")
def accounts():
    conn = get_db()
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    s = get_settings()
    oauth_status = {}
    for pid, cfg in OAUTH_PLATFORMS.items():
        first_field = cfg["cred_fields"][0][0]
        has_creds = bool(s.get(f"oauth_{pid}_{first_field}", ""))
        has_token = bool(s.get(f"oauth_{pid}_access_token", ""))
        oauth_status[pid] = {"has_creds": has_creds, "has_token": has_token}
    conn.close()
    redirect_base = "https://" + os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
    return render_template("accounts.html", active="accounts", accounts=rows,
                       oauth_status=oauth_status, oauth_platforms=OAUTH_PLATFORMS,
                       redirect_base=redirect_base)
    

@app.route("/accounts/add", methods=["POST"])
def accounts_add():
    platform = request.form.get("platform", "").strip()
    username = request.form.get("username", "").strip()
    if not platform or not username:
        flash("Platform and username are required.", "error")
        return redirect(url_for("accounts"))
    conn = get_db()
    conn.execute("INSERT INTO accounts (platform, username, enabled) VALUES (?, ?, 1)", (platform, username))
    conn.commit()
    conn.close()
    flash(f"{platform} account added successfully.", "success")
    return redirect(url_for("accounts"))


@app.route("/accounts/toggle/<int:account_id>", methods=["POST"])
def accounts_toggle(account_id):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM accounts WHERE id=?", (account_id,)).fetchone()
    if row:
        conn.execute("UPDATE accounts SET enabled=? WHERE id=?", (0 if row["enabled"] else 1, account_id))
        conn.commit()
    conn.close()
    return redirect(url_for("accounts"))


@app.route("/accounts/delete/<int:account_id>", methods=["POST"])
def accounts_delete(account_id):
    conn = get_db()
    conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()
    flash("Account removed.", "success")
    return redirect(url_for("accounts"))


DEFAULT_TIMES = ["12:00", "16:00", "20:00"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
PLATFORM_ICONS = {"TikTok": "📱", "Instagram": "📸", "YouTube": "🖥", "All": "🌐"}


def _week_start_from_str(s):
    if s:
        try:
            d = date.fromisoformat(s)
            return d - timedelta(days=d.weekday())
        except Exception:
            pass
    today = date.today()
    return today - timedelta(days=today.weekday())


def _auto_update_statuses(conn):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "UPDATE scheduled_posts SET status='done' "
        "WHERE status='scheduled' AND (schedule_date || ' ' || schedule_time) < ?",
        (now_str,)
    )
    conn.commit()


@app.route("/schedule")
def schedule():
    week_start = _week_start_from_str(request.args.get("week_start"))
    week_end = week_start + timedelta(days=6)

    conn = get_db()
    _auto_update_statuses(conn)

    posts = conn.execute(
        "SELECT * FROM scheduled_posts WHERE schedule_date >= ? AND schedule_date <= ? ORDER BY schedule_date, schedule_time",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchall()

    all_posts = conn.execute(
        "SELECT * FROM scheduled_posts ORDER BY schedule_date ASC, schedule_time ASC"
    ).fetchall()

    queue_items = conn.execute(
        "SELECT * FROM queue WHERE status='pending' ORDER BY sort_order ASC, added_at ASC"
    ).fetchall()

    summary = {"scheduled": 0, "done": 0, "failed": 0}
    for p in posts:
        if p["status"] in summary:
            summary[p["status"]] += 1

    conn.close()

    today = date.today()
    calendar_data = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_str = day.isoformat()
        day_posts = {p["schedule_time"]: p for p in posts if p["schedule_date"] == day_str}
        all_times = sorted(set(DEFAULT_TIMES) | set(day_posts.keys()))
        slots = [{"time": t, "post": day_posts.get(t)} for t in all_times]
        calendar_data.append({
            "date_str": day_str,
            "day_name": DAY_NAMES[i],
            "day_num": day.day,
            "month_name": MONTH_NAMES[day.month - 1],
            "is_today": day == today,
            "is_weekend": i >= 5,
            "slots": slots,
        })

    week_label = (
        f"{MONTH_NAMES[week_start.month-1]} {week_start.day} - "
        f"{MONTH_NAMES[week_end.month-1]} {week_end.day}, {week_end.year}"
    )
    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    conn2 = get_db()
    connected_accounts = conn2.execute("SELECT * FROM accounts WHERE enabled=1 ORDER BY platform, username").fetchall()
    conn2.close()
    return render_template("schedule.html", active="schedule",
                           calendar_data=calendar_data,
                           all_posts=all_posts,
                           week_start_str=week_start.isoformat(),
                           week_label=week_label,
                           prev_week=prev_week,
                           next_week=next_week,
                           summary=summary,
                           queue_items=queue_items,
                           platform_icons=PLATFORM_ICONS,
                           connected_accounts=connected_accounts)


@app.route("/schedule/add", methods=["POST"])
def schedule_add():
    post_id = request.form.get("post_id", "").strip()
    sdate = request.form.get("schedule_date", "").strip()
    stime = request.form.get("schedule_time", "").strip()
    platform = request.form.get("platform", "All").strip()
    video_id = request.form.get("video_id", "").strip() or None
    clip_title = request.form.get("clip_title", "").strip() or None
    caption = request.form.get("caption", "").strip() or None
    week_start = request.form.get("week_start", "")

    if not sdate or not stime:
        flash("Date and time are required.", "error")
        return redirect(url_for("schedule") + f"?week_start={week_start}")

    conn = get_db()
    if post_id:
        conn.execute(
            "UPDATE scheduled_posts SET schedule_date=?,schedule_time=?,platform=?,video_id=?,clip_title=?,caption=? WHERE id=?",
            (sdate, stime, platform, video_id, clip_title, caption, int(post_id))
        )
        flash("Schedule updated.", "success")
    else:
        conn.execute(
            "INSERT INTO scheduled_posts (schedule_date,schedule_time,platform,video_id,clip_title,caption,status) VALUES (?,?,?,?,?,?,?)",
            (sdate, stime, platform, video_id, clip_title, caption, "scheduled")
        )
        flash("Scheduled.", "success")
    conn.commit()
    conn.close()
    return redirect(url_for("schedule") + f"?week_start={week_start}")


@app.route("/schedule/delete/<int:post_id>", methods=["POST"])
def schedule_delete(post_id):
    week_start = request.form.get("week_start", "")
    conn = get_db()
    conn.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()
    flash("Removed.", "success")
    return redirect(url_for("schedule") + f"?week_start={week_start}")


@app.route("/schedule/auto-fill", methods=["POST"])
def schedule_auto_fill():
    week_start = _week_start_from_str(request.form.get("week_start"))
    week_end = week_start + timedelta(days=6)

    conn = get_db()
    queue_items = conn.execute(
        "SELECT * FROM queue WHERE status='pending' ORDER BY sort_order ASC, added_at ASC"
    ).fetchall()

    existing = conn.execute(
        "SELECT schedule_date, schedule_time FROM scheduled_posts WHERE schedule_date >= ? AND schedule_date <= ?",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchall()
    existing_slots = {(r["schedule_date"], r["schedule_time"]) for r in existing}

    idx = 0
    filled = 0
    for i in range(7):
        day_str = (week_start + timedelta(days=i)).isoformat()
        for t in DEFAULT_TIMES:
            if (day_str, t) not in existing_slots and idx < len(queue_items):
                item = queue_items[idx]
                conn.execute(
                    "INSERT INTO scheduled_posts (schedule_date,schedule_time,platform,video_id,clip_title,status) VALUES (?,?,?,?,?,?)",
                    (day_str, t, "All", item["video_id"], item["title"], "scheduled")
                )
                idx += 1
                filled += 1

    conn.commit()
    conn.close()
    flash(f"Auto-filled {filled} slots from queue.", "success")
    return redirect(url_for("schedule") + f"?week_start={week_start.isoformat()}")


@app.route("/schedule/copy-week", methods=["POST"])
def schedule_copy_week():
    week_start = _week_start_from_str(request.form.get("week_start"))
    week_end = week_start + timedelta(days=6)
    next_start = week_start + timedelta(weeks=1)

    conn = get_db()
    posts = conn.execute(
        "SELECT * FROM scheduled_posts WHERE schedule_date >= ? AND schedule_date <= ?",
        (week_start.isoformat(), week_end.isoformat())
    ).fetchall()

    copied = 0
    for p in posts:
        new_date = (date.fromisoformat(p["schedule_date"]) + timedelta(weeks=1)).isoformat()
        exists = conn.execute(
            "SELECT id FROM scheduled_posts WHERE schedule_date=? AND schedule_time=?",
            (new_date, p["schedule_time"])
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO scheduled_posts (schedule_date,schedule_time,platform,video_id,clip_title,caption,status) VALUES (?,?,?,?,?,?,?)",
                (new_date, p["schedule_time"], p["platform"], p["video_id"], p["clip_title"], p["caption"], "scheduled")
            )
            copied += 1

    conn.commit()
    conn.close()
    flash(f"Copied {copied} schedules to next week.", "success")
    return redirect(url_for("schedule") + f"?week_start={next_start.isoformat()}")


@app.route("/schedule/clear-week", methods=["POST"])
def schedule_clear_week():
    week_start = _week_start_from_str(request.form.get("week_start"))
    week_end = (week_start + timedelta(days=6)).isoformat()
    conn = get_db()
    conn.execute(
        "DELETE FROM scheduled_posts WHERE schedule_date >= ? AND schedule_date <= ?",
        (week_start.isoformat(), week_end)
    )
    conn.commit()
    conn.close()
    flash("Week cleared.", "success")
    return redirect(url_for("schedule") + f"?week_start={week_start.isoformat()}")


@app.route("/settings")
def settings():
    s = get_settings()
    env_key_set = bool(os.environ.get("YOUTUBE_API_KEY", "").strip())
    db_key = s.get("youtube_api_key", "").strip()
    db_key_set = bool(db_key)
    masked_key = ""
    api_key_configured = env_key_set or db_key_set
    return render_template("settings.html", active="settings", settings=s,
                           env_key_set=env_key_set, db_key_set=db_key_set,
                           masked_key=masked_key,
                           api_key_configured=api_key_configured)


@app.route("/settings/update", methods=["POST"])
def settings_update():
    genres = ",".join(request.form.getlist("genres")) or "Tech"
    clip_duration = request.form.get("clip_duration", "60")
    viral_score_min = request.form.get("viral_score_min", "60")
    clips_per_day = request.form.get("clips_per_day", "3")
    conn = get_db()
    for key, val in [
        ("genres", genres),
        ("clip_duration", clip_duration),
        ("viral_score_min", viral_score_min),
        ("clips_per_day", clips_per_day),
    ]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()
    flash("Settings saved.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/save-api-key", methods=["POST"])
def settings_save_api_key():
    key = request.form.get("youtube_api_key", "").strip()
    if not key:
        flash("API key cannot be empty.", "error")
        return redirect(url_for("settings"))
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("youtube_api_key", key))
    conn.commit()
    conn.close()
    flash("YouTube API key saved.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/clear-api-key", methods=["POST"])
def settings_clear_api_key():
    conn = get_db()
    conn.execute("DELETE FROM settings WHERE key='youtube_api_key'")
    conn.commit()
    conn.close()
    flash("API key cleared.", "success")
    return redirect(url_for("settings"))

@app.route("/analyzer")
def analyzer():
    return render_template("link_analyzer.html", active="analyzer")

@app.route("/analyzer/analyze", methods=["POST"])
def analyzer_analyze():
    api_key = get_api_key()
    if not api_key:
        return jsonify({"ok": False, "error": "YouTube API key not configured. Go to Settings."}), 400
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])
    if not urls:
        return jsonify({"ok": False, "error": "No URLs provided"}), 400
    try:
        results = analyze_links(api_key, urls)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/terms")
def terms():
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "terms_of_service.html")
    if os.path.exists(path):
        return open(path).read()
    return "<h1>Terms of Service</h1><p>ViralCut Pro terms of service. Contact: viralcutpro@gmail.com</p>", 200

@app.route("/tiktokrBMGfpNh4W6PXRMQAVrp9t5ZTQM7Ee5Y.txt")
def tiktok_verify():
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "tiktokrBMGfpNh4W6PXRMQAVrp9t5ZTQM7Ee5Y.txt")
    if os.path.exists(path):
        return open(path).read(), 200, {"Content-Type": "text/plain"}
    return "tiktokrBMGfpNh4W6PXRMQAVrp9t5ZTQM7Ee5Y", 200, {"Content-Type": "text/plain"}

@app.route("/privacy")
def privacy():
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "privacy_policy.html")
    if os.path.exists(path):
        return open(path).read()
    return "<h1>Privacy Policy</h1><p>ViralCut Pro does not sell your data. Contact: viralcutpro@gmail.com</p>", 200

@app.route("/upload/youtube", methods=["POST"])
def upload_youtube():
    data = request.get_json(silent=True) or {}
    queue_id = data.get("queue_id", "")
    if not queue_id:
        return jsonify({"ok": False, "error": "queue_id required"}), 400

    conn = get_db()
    item = conn.execute("SELECT * FROM queue WHERE id=?", (queue_id,)).fetchone()
    conn.close()
    if not item:
        return jsonify({"ok": False, "error": "Queue item not found"}), 404

    settings = get_settings()
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
    redirect_uri = f"https://{domain}/oauth/callback/youtube"

    try:
        from youtube_upload import get_valid_access_token, upload_video_to_youtube
        from video_processor import process_full_pipeline, CLIPS_DIR

        token_result = get_valid_access_token(settings, redirect_uri)
        access_token = token_result[0] if isinstance(token_result, tuple) else token_result

        video_id = item["video_id"]
        title = item["title"] or "ViralCut Pro"
        caption = item["notes"] or ""
        duration = item["duration"] or 60

        conn = get_db()
        conn.execute("UPDATE queue SET status='processing' WHERE id=?", (queue_id,))
        conn.commit()
        conn.close()

        result = process_full_pipeline(
            video_id=video_id,
            start_sec=0,
            end_sec=duration,
            output_format="portrait",
            quality="720p",
            remove_bgm=False,
        )

        upload_result = upload_video_to_youtube(
            access_token=access_token,
            video_path=result["clip_path"],
            title=title[:100],
            description=caption,
            tags=["viral","trending","shorts","indonesia"],
            privacy="public",
        )

        import os as _os
        if _os.path.exists(result["clip_path"]):
            _os.remove(result["clip_path"])

        conn = get_db()
        conn.execute("UPDATE queue SET status='posted' WHERE id=?", (queue_id,))
        conn.commit()
        conn.close()

        return jsonify(upload_result)

    except Exception as e:
        conn = get_db()
        conn.execute("UPDATE queue SET status='failed' WHERE id=?", (queue_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/upload/channel-info")
def upload_channel_info():
    settings = get_settings()
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
    redirect_uri = f"https://{domain}/oauth/callback/youtube"
    try:
        token = get_valid_access_token(settings, redirect_uri)
        if isinstance(token, tuple): token = token[0]
        info = get_channel_info(token)
        return jsonify({"ok": True, **info})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/process/clip", methods=["POST"])
def process_clip_route():
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id","").strip()
    start_sec = float(data.get("start_sec", 0))
    end_sec = float(data.get("end_sec", 60))
    output_format = data.get("format","portrait")
    quality = data.get("quality","720p")
    caption = data.get("caption","")
    remove_bgm = data.get("remove_bgm", False)
    if not video_id:
        return jsonify({"ok":False,"error":"video_id required"}), 400
    try:
        result = process_full_pipeline(video_id, start_sec, end_sec, output_format, quality, caption, remove_bgm)
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                    (f"clip_file_{video_id}", result["clip_filename"]))
        conn.commit()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/clips/download/<filename>")
def download_clip(filename):
    import send_file as sf
    safe = os.path.basename(filename)
    path = os.path.join(CLIPS_DIR, safe)
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, as_attachment=True, download_name=safe)

@app.route("/system/check")
def system_check():
    return jsonify({
        "ffmpeg": check_ffmpeg(),
        "ytdlp": check_ytdlp(),
        "scheduler": "running"
    })
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
