"""
Auto-upload scheduler using APScheduler.
Runs in background thread, checks schedule every minute,
uploads clips to YouTube when time matches.
"""
import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler = None


def start_scheduler(app):
    """Start the background scheduler with app context."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    _scheduler.add_job(
        func=lambda: run_scheduled_uploads(app),
        trigger="interval",
        minutes=1,
        id="auto_upload",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — checking every minute for uploads")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()


def run_scheduled_uploads(app):
    """
    Check if current time matches any scheduled post,
    and upload the next pending clip in queue.
    """
    with app.app_context():
        try:
            from db import get_db
            from youtube_upload import get_valid_access_token, upload_video_to_youtube

            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")

            conn = get_db()

            # Check scheduled_posts table for posts due now
            due_posts = conn.execute(
                """SELECT * FROM scheduled_posts
                   WHERE schedule_date = ? AND schedule_time = ?
                   AND status = 'scheduled'
                   ORDER BY id ASC LIMIT 1""",
                (current_date, current_time)
            ).fetchall()

            # Also check legacy schedule slots
            if not due_posts:
                active_slots = conn.execute(
                    "SELECT * FROM schedule WHERE enabled=1 AND slot_time=?",
                    (current_time,)
                ).fetchall()
                if not active_slots:
                    conn.close()
                    return

                # Get next pending clip from queue
                pending = conn.execute(
                    """SELECT * FROM queue WHERE status='pending'
                       ORDER BY sort_order ASC, added_at ASC LIMIT 1"""
                ).fetchone()

                if not pending:
                    conn.close()
                    return

                _do_upload_from_queue(conn, pending, current_date, current_time)
            else:
                for post in due_posts:
                    _do_upload_scheduled_post(conn, post)

            conn.close()

        except Exception as e:
            logger.error(f"Scheduler error: {e}")


def _do_upload_from_queue(conn, queue_item, date_str, time_str):
    """Upload a clip from the queue to YouTube."""
    try:
        from db import get_db as _get_db
        from youtube_upload import get_valid_access_token, upload_video_to_youtube
        from video_processor import process_full_pipeline, CLIPS_DIR
        import os

        # Get settings
        settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {r["key"]: r["value"] for r in settings_rows} if settings_rows else {}

        domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
        redirect_uri = f"https://{domain}/oauth/callback/youtube"

        # Get access token
        try:
            token_result = get_valid_access_token(settings, redirect_uri)
            access_token = token_result[0] if isinstance(token_result, tuple) else token_result
        except Exception as e:
            logger.error(f"No YouTube token: {e}")
            return

        video_id = queue_item["video_id"]
        title = queue_item["title"] or "ViralCut Pro Upload"
        caption = queue_item["notes"] or ""
        duration = queue_item["duration"] or 60

        # Check if we already have a processed clip
        clip_filename = settings.get(f"clip_file_{video_id}", "")
        clip_path = os.path.join(CLIPS_DIR, clip_filename) if clip_filename else ""

        if not clip_path or not os.path.exists(clip_path):
            # Need to download and process
            logger.info(f"Processing clip for video_id: {video_id}")
            conn.execute(
                "UPDATE queue SET status='processing' WHERE id=?",
                (queue_item["id"],)
            )
            conn.commit()

            try:
                result = process_full_pipeline(
                    video_id=video_id,
                    start_sec=0,
                    end_sec=duration,
                    output_format="portrait",
                    quality="720p",
                    remove_bgm=False,
                )
                clip_path = result["clip_path"]
            except Exception as e:
                logger.error(f"Processing failed: {e}")
                conn.execute(
                    "UPDATE queue SET status='failed' WHERE id=?",
                    (queue_item["id"],)
                )
                conn.commit()
                return

        # Upload to YouTube
        logger.info(f"Uploading to YouTube: {title}")
        conn.execute(
            "UPDATE queue SET status='uploading' WHERE id=?",
            (queue_item["id"],)
        )
        conn.commit()

        upload_result = upload_video_to_youtube(
            access_token=access_token,
            video_path=clip_path,
            title=title[:100],
            description=caption,
            tags=["viral", "trending", "shorts", "indonesia"],
            privacy="public",
        )

        if upload_result.get("ok"):
            conn.execute(
                "UPDATE queue SET status='posted' WHERE id=?",
                (queue_item["id"],)
            )
            # Log to scheduled_posts
            conn.execute(
                """INSERT INTO scheduled_posts
                   (schedule_date, schedule_time, platform, video_id, clip_title, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date_str, time_str, "YouTube",
                 upload_result.get("video_id", ""),
                 title, "done")
            )
            conn.commit()
            logger.info(f"✓ Uploaded: {upload_result.get('url')}")

            # Cleanup clip file after upload
            if os.path.exists(clip_path):
                os.remove(clip_path)
        else:
            conn.execute(
                "UPDATE queue SET status='failed' WHERE id=?",
                (queue_item["id"],)
            )
            conn.commit()

    except Exception as e:
        logger.error(f"Upload error: {e}")
        try:
            conn.execute(
                "UPDATE queue SET status='failed' WHERE id=?",
                (queue_item["id"],)
            )
            conn.commit()
        except Exception:
            pass


def _do_upload_scheduled_post(conn, post):
    """Upload a specifically scheduled post."""
    try:
        conn.execute(
            "UPDATE scheduled_posts SET status='done' WHERE id=?",
            (post["id"],)
        )
        conn.commit()
        logger.info(f"Processed scheduled post {post['id']}")
    except Exception as e:
        logger.error(f"Scheduled post error: {e}")
