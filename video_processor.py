import os
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
        subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5)
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
        "yt-dlp",
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

    # Download video
    download_cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-playlist",
        "--socket-timeout", "30",
        url
    ]

    result = subprocess.run(
        download_cmd, capture_output=True, text=True, timeout=300
    )

    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr[-500:]}")

    # Find the downloaded file
    file_path = None
    for ext in ["mp4", "webm", "mkv"]:
        candidate = os.path.join(DOWNLOADS_DIR, f"{video_id}.{ext}")
        if os.path.exists(candidate):
            file_path = candidate
            break

    if not file_path:
        raise Exception("Downloaded file not found")

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
