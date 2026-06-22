import os
import re
import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in patterns:
        m = re.search(p, url.strip())
        if m:
            return m.group(1)
    return ""


def get_video_details(api_key: str, video_ids: list) -> list:
    """Fetch full video details from YouTube API."""
    if not video_ids:
        return []
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=12)
    resp.raise_for_status()
    return resp.json().get("items", [])


def parse_duration(iso: str) -> int:
    """Convert ISO 8601 duration to seconds."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mn * 60 + s


def format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def score_segment(title: str, description: str, views: int, likes: int,
                  comments: int, duration_sec: int) -> dict:
    """
    Analyze video and generate potential viral segments with timestamps.
    Returns list of segments with start/end times and viral potential score.
    """
    segments = []
    desc_lower = (description or "").lower()
    title_lower = title.lower()

    # Hook detection — first 30 seconds always high potential
    segments.append({
        "label": "Hook / Opening",
        "start": 0,
        "end": min(30, duration_sec),
        "reason": "First 30 seconds — highest retention & share potential",
        "potential": "🔥 Very High",
        "clip_duration": 30,
        "cc_style": "Bold hook caption to grab attention instantly",
    })

    # Mid-point peak — usually where the main value is
    if duration_sec > 120:
        mid = duration_sec // 3
        segments.append({
            "label": "Main Value / Peak Moment",
            "start": mid,
            "end": min(mid + 60, duration_sec),
            "reason": "Core content — highest information density",
            "potential": "🔥 High",
            "clip_duration": 60,
            "cc_style": "Informative caption with key takeaway",
        })

    # Climax / reveal — 2/3 through video
    if duration_sec > 180:
        climax = (duration_sec * 2) // 3
        segments.append({
            "label": "Climax / Reveal",
            "start": climax,
            "end": min(climax + 90, duration_sec),
            "reason": "Revelation or emotional peak — high shareability",
            "potential": "⚡ High",
            "clip_duration": 90,
            "cc_style": "Dramatic caption to maximize emotional impact",
        })

    # Ending CTA — last 30 seconds
    if duration_sec > 60:
        end_start = max(0, duration_sec - 30)
        segments.append({
            "label": "Ending / Call to Action",
            "start": end_start,
            "end": duration_sec,
            "reason": "Strong CTA moments drive follows and saves",
            "potential": "📈 Medium-High",
            "clip_duration": 30,
            "cc_style": "CTA caption: follow for more, save this video",
        })

    # Detect chapters from description
    chapter_pattern = re.findall(r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.+)', description or "")
    for ch in chapter_pattern[:3]:
        h_val = 0
        if len(ch) == 4 and ch[2]:
            h_val = int(ch[0])
            m_val = int(ch[1])
            s_val = int(ch[2])
            label = ch[3]
        else:
            m_val = int(ch[0])
            s_val = int(ch[1])
            label = ch[3] if len(ch) > 3 else ch[2]
        ts = h_val * 3600 + m_val * 60 + s_val
        if ts < duration_sec - 30:
            segments.append({
                "label": f"Chapter: {label.strip()[:40]}",
                "start": ts,
                "end": min(ts + 60, duration_sec),
                "reason": "Creator-marked chapter — pre-segmented content",
                "potential": "⚡ High",
                "clip_duration": 60,
                "cc_style": "Chapter caption with topic context",
            })

    # Calculate viral score per segment
    base_score = min(40, int((views / 1_000_000) * 8))
    like_ratio = (likes / views * 100) if views > 0 else 0
    eng_score = min(20, int(like_ratio * 5))
    comment_score = min(10, int((comments / views * 1000))) if views > 0 else 0

    for i, seg in enumerate(segments):
        position_bonus = max(0, 5 - i) * 2
        seg["viral_score"] = min(99, 30 + base_score + eng_score + comment_score + position_bonus)
        seg["start_fmt"] = _fmt_time(seg["start"])
        seg["end_fmt"] = _fmt_time(seg["end"])

    segments.sort(key=lambda x: x["viral_score"], reverse=True)
    return segments


def _fmt_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def generate_cc(title: str, genre: str, segment_label: str,
                cc_style: str, clip_duration: int) -> dict:
    """Generate caption/CC suggestions for a clip segment."""
    title_clean = title[:50]

    hooks = {
        "Hook / Opening": [
            f"Wait for it... 🤯",
            f"This changed everything about {genre.lower()} content",
            f"Nobody talks about this 👇",
        ],
        "Main Value / Peak Moment": [
            f"Here's the part everyone's sharing 🔥",
            f"This is the key moment you need to see",
            f"Save this — you'll thank me later ✅",
        ],
        "Climax / Reveal": [
            f"The reveal that broke the internet 😱",
            f"I can't believe this actually worked",
            f"Plot twist nobody saw coming 👀",
        ],
        "Ending / Call to Action": [
            f"Follow for more {genre} content 🙏",
            f"Like if this helped you! 💜",
            f"Share this with someone who needs to see it",
        ],
    }

    default_hooks = [
        f"This {genre.lower()} content is 🔥",
        f"Going viral for a reason 📈",
        f"You need to see this",
    ]

    hook_list = hooks.get(segment_label, default_hooks)

    captions = {
        "short": f"{hook_list[0]}\n\n#{genre.lower()} #viral #trending #indonesia",
        "medium": (
            f"{hook_list[0]}\n\n"
            f"From: {title_clean}\n\n"
            f"#{genre.lower()} #viral #trending #fyp #indonesia"
        ),
        "long": (
            f"{hook_list[0]}\n\n"
            f"Clip dari: {title_clean}\n\n"
            f"{cc_style}\n\n"
            f"Duration: {clip_duration}s\n\n"
            f"#{genre.lower()} #viral #trending #fyp #foryou #indonesia #kontenlokal"
        ),
    }

    return captions


def analyze_links(api_key: str, urls: list) -> list:
    """
    Main function: analyze multiple YouTube URLs,
    return list of videos with segments and CC.
    """
    # Extract and validate video IDs
    video_ids = []
    url_map = {}
    for url in urls:
        vid = extract_video_id(url.strip())
        if vid and vid not in video_ids:
            video_ids.append(vid)
            url_map[vid] = url.strip()

    if not video_ids:
        return []

    # Fetch details from YouTube API
    items = get_video_details(api_key, video_ids)

    results = []
    for item in items:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        title = snippet.get("title", "")
        description = snippet.get("description", "")
        channel = snippet.get("channelTitle", "")
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        duration_iso = content.get("duration", "PT0S")
        duration_sec = parse_duration(duration_iso)

        thumbs = snippet.get("thumbnails", {})
        thumbnail = (
            thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}
        ).get("url", "")

        published = snippet.get("publishedAt", "")[:10]

        # Detect genre from title
        from youtube import detect_genre
        genre = detect_genre(snippet.get("categoryId", ""), title)

        # Generate segments
        segments = score_segment(
            title, description, views, likes, comments, duration_sec
        )

        # Generate CC for each segment
        for seg in segments:
            seg["captions"] = generate_cc(
                title, genre, seg["label"], seg["cc_style"], seg["clip_duration"]
            )

        results.append({
            "video_id": item["id"],
            "url": url_map.get(item["id"], ""),
            "title": title,
            "channel": channel,
            "thumbnail": thumbnail,
            "views": format_count(views),
            "views_raw": views,
            "likes": format_count(likes),
            "comments": format_count(comments),
            "published": published,
            "duration_sec": duration_sec,
            "duration_fmt": _fmt_time(duration_sec),
            "genre": genre,
            "segments": segments,
        })

    # Sort by views
    results.sort(key=lambda x: x["views_raw"], reverse=True)
    return results
