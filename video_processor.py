import os
import sys
import subprocess
import uuid
import json
import requests
import time

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def check_ytdlp() -> bool:
    """Check if yt-dlp is available."""
    try:
        subprocess.run([sys.executable, "-m", "yt_dlp", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def download_youtube_video(video_id: str, quality: str = "720") -> dict:
    """
    Download a YouTube video using yt-dlp.
    Returns dict with file_path, title, duration.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_path = os.path.join(DOWNLOADS_DIR, f"{video_id}.%(ext)s")

    # Get video info first
    info_cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json",
        "--no-playlist",
        url
    ]
    try:
        info_result = subprocess.run(
            info_cmd, capture_output=True, text=True, timeout=30
        )
        info = json.loads(info_result.stdout)
        title = info.get("title", video_id)
        duration = info.get("duration", 0)
    except Exception:
        title = video_id
        duration = 0

    # Download video — try progressively simpler formats until one works
    # Railway IPs often can't access DASH (split video+audio) streams,
    # so we fall back to single-file formats that bundle video+audio together.
    format_attempts = [
        # Best: separate video+audio merged to mp4
        f"bestvideo[vcodec!=none][height<={quality}]+bestaudio/bestvideo[vcodec!=none]+bestaudio",
        # Good: any format with video, up to quality height
        f"best[vcodec!=none][height<={quality}]/best[vcodec!=none]",
        # Last resort: absolute best single file (may be lower quality)
        "best",
    ]

    result = None
    last_error = ""
    for fmt in format_attempts:
        download_cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", fmt,
            "--merge-output-format", "mp4",
            "--no-check-certificate",
            "-o", output_path,
            "--no-playlist",
            "--socket-timeout", "30",
            "--retries", "3",
            "--fragment-retries", "3",
            url
        ]
        result = subprocess.run(
            download_cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            break
        last_error = result.stderr[-300:]

    if result is None or result.returncode != 0:
        raise Exception(f"Download failed after all format attempts: {last_error}")

    # Find the downloaded file
    file_path = None
    for ext in ["mp4", "webm", "mkv"]:
        candidate = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
        if os.path.exists(candidate):
            file_path = candidate
            break

    if not file_path:
        raise Exception("Downloaded file not found after successful yt-dlp run")

    # Verify the file actually has a video stream (not just audio)
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", file_path
    ]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
    if not probe.stdout.strip():
        os.remove(file_path)
        raise Exception(
            "yt-dlp downloaded audio-only file — YouTube may be throttling this server. "
            "Try again in a few minutes."
        )

    return {
        "file_path": file_path,
        "title": title,
        "duration": duration,
        "video_id": video_id,
    }


def cut_clip(
    input_path: str,
    start_sec: float,
    end_sec: float,
    output_format: str = "portrait",
    quality: str = "1080p",
    add_caption: str = "",
    remove_bgm: bool = False,
) -> str:
    """
    Cut a clip from video with ffmpeg.
    output_format: portrait (9:16), landscape (16:9), square (1:1)
    Returns path to output clip file.
    """
    clip_id = uuid.uuid4().hex[:12]
    output_path = os.path.join(CLIPS_DIR, f"clip_{clip_id}.mp4")
    duration = end_sec - start_sec

    # Build video filter
    if output_format == "portrait":
        # 9:16 for TikTok/Reels/Shorts - crop to vertical
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    elif output_format == "square":
        # 1:1 for Instagram feed
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    else:
        # 16:9 landscape default
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

    # Quality settings
    quality_map = {"720p": "720", "1080p": "1080", "4k": "2160"}
    height = quality_map.get(quality, "1080")

    # Build ffmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
    ]

    # Audio handling
    if remove_bgm:
        cmd.extend(["-an"])  # Remove all audio
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise Exception(f"FFmpeg error: {result.stderr[-500:]}")

    if not os.path.exists(output_path):
        raise Exception("Output clip not created")

    return output_path


def get_clip_info(clip_path: str) -> dict:
    """Get duration and size of a clip."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", clip_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        size = int(data.get("format", {}).get("size", 0))
        return {
            "duration": round(duration, 1),
            "size_mb": round(size / 1024 / 1024, 1),
            "path": clip_path,
        }
    except Exception:
        return {"duration": 0, "size_mb": 0, "path": clip_path}


def cleanup_downloads(video_id: str):
    """Remove downloaded source video to save space."""
    for ext in ["mp4", "webm", "mkv", "m4a"]:
        path = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
        if os.path.exists(path):
            os.remove(path)


def process_full_pipeline(
    video_id: str,
    start_sec: float,
    end_sec: float,
    output_format: str = "portrait",
    quality: str = "1080p",
    caption: str = "",
    remove_bgm: bool = False,
) -> dict:
    """
    Full pipeline: download → cut → return clip path.
    This is the main function called from the web app.
    """
    # Download
    download_info = download_youtube_video(video_id, quality="720")
    source_path = download_info["file_path"]

    try:
        # Cut clip
        clip_path = cut_clip(
            source_path, start_sec, end_sec,
            output_format, quality, caption, remove_bgm
        )

        # Get clip info
        clip_info = get_clip_info(clip_path)

        # Cleanup source to save space
        cleanup_downloads(video_id)

        return {
            "ok": True,
            "clip_path": clip_path,
            "clip_filename": os.path.basename(clip_path),
            "duration": clip_info["duration"],
            "size_mb": clip_info["size_mb"],
            "title": download_info["title"],
        }

    except Exception as e:
        cleanup_downloads(video_id)
        raise e
