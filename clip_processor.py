import os
import uuid
import json
import subprocess

UPLOAD_DIR    = os.path.join(os.path.dirname(__file__), "uploads")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "processed")

os.makedirs(UPLOAD_DIR,    exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# ffmpeg crop/scale filters per output format
FORMAT_FILTERS = {
    "portrait":  "crop=ih*9/16:ih,scale=1080:1920",
    "landscape": "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
    "square":    "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080",
}

QUALITY_SETTINGS = {
    "1080p": ("4000k", "192k"),
    "720p":  ("2000k", "128k"),
}


def get_video_info(file_id: str) -> dict:
    path = os.path.join(UPLOAD_DIR, os.path.basename(file_id))
    if not os.path.exists(path):
        return {"duration": 0, "width": 0, "height": 0}
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=20, text=True)
        data = json.loads(res.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        width = height = 0
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                width  = s.get("width",  0)
                height = s.get("height", 0)
                break
        return {"duration": round(duration, 3), "width": width, "height": height}
    except Exception:
        return {"duration": 0, "width": 0, "height": 0}


def process_clip(
    file_id: str,
    start_sec: float,
    end_sec: float | None,
    fmt: str,
    quality: str,
    output_ext: str = "mp4",
) -> tuple[str | None, str | None]:
    """
    Trim and optionally reformat a video using ffmpeg.
    Returns (output_filename, error_message).
    """
    input_path = os.path.join(UPLOAD_DIR, os.path.basename(file_id))
    if not os.path.exists(input_path):
        return None, "Uploaded file not found on server"

    output_name = f"{uuid.uuid4().hex}.{output_ext}"
    output_path = os.path.join(PROCESSED_DIR, output_name)

    vb, ab = QUALITY_SETTINGS.get(quality, ("2000k", "128k"))
    vf = FORMAT_FILTERS.get(fmt)

    cmd = ["ffmpeg", "-y"]

    # Fast input seek (before -i for keyframe-accurate start)
    if start_sec and start_sec > 0:
        cmd += ["-ss", f"{start_sec:.3f}"]

    cmd += ["-i", input_path]

    # Duration (relative to seek point)
    if end_sec is not None and end_sec > (start_sec or 0):
        duration = end_sec - (start_sec or 0)
        cmd += ["-t", f"{duration:.3f}"]

    if vf:
        cmd += ["-vf", vf]

    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-b:v", vb,
        "-c:a", "aac",
        "-b:a", ab,
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
        if result.returncode != 0:
            err_tail = (result.stderr or "")[-600:].strip()
            return None, err_tail or "ffmpeg returned non-zero exit code"
        if not os.path.exists(output_path):
            return None, "ffmpeg ran but output file was not created"
        return output_name, None
    except subprocess.TimeoutExpired:
        return None, "Processing timed out (max 5 minutes)"
    except Exception as exc:
        return None, str(exc)
