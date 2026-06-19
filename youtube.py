import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# YouTube category IDs → app genres
CATEGORY_GENRE_MAP = {
    "1":  "Lifestyle",    # Film & Animation
    "2":  "Automotive",   # Autos & Motorcycles
    "10": "Music",        # Music
    "15": "Lifestyle",    # Pets & Animals
    "17": "Sports",       # Sports
    "19": "Lifestyle",    # Travel & Events
    "20": "Gaming",       # Gaming
    "21": "Lifestyle",    # Videoblogging
    "22": "Lifestyle",    # People & Blogs
    "23": "Lifestyle",    # Comedy
    "24": "Lifestyle",    # Entertainment
    "25": "Lifestyle",    # News & Politics
    "26": "DIY",          # Howto & Style
    "27": "Tech",         # Education
    "28": "Tech",         # Science & Technology
    "29": "Lifestyle",    # Nonprofits
}

TITLE_KEYWORDS = {
    "Automotive": ["car", "truck", "motor", "bike", "vehicle", "engine", "drift", "racing",
                   "mobil", "modif", "otomotif", "vespa", "honda", "toyota", "suzuki", "balap"],
    "Food":       ["food", "recipe", "cooking", "eat", "restaurant", "bake", "chef", "mukbang",
                   "masak", "makan", "resep", "kuliner", "makanan", "minuman", "kue", "jajan"],
    "DIY":        ["diy", "build", "craft", "woodwork", "renovation", "repair", "tutorial", "how to",
                   "cara", "buat", "bikin", "renovasi", "dekorasi", "kreasi"],
    "Tech":       ["tech", "phone", "app", "software", "ai", "gadget", "coding", "review",
                   "iphone", "android", "laptop", "unboxing", "setup", "pc", "komputer"],
    "Gaming":     ["game", "gaming", "play", "minecraft", "roblox", "mobile legend", "mlbb",
                   "ff", "pubg", "genshin", "stream", "esport", "valorant", "lego"],
    "Music":      ["music", "song", "official", "mv", "music video", "lyric", "cover",
                   "lagu", "official video", "single", "album", "konser", "nyanyi", "ost"],
    "Sports":     ["sport", "football", "soccer", "basket", "badminton", "tennis", "race",
                   "bola", "sepak bola", "olahraga", "tinju", "atletik", "juara"],
    "Lifestyle":  ["vlog", "day in", "routine", "travel", "fashion", "style", "tips", "challenge",
                   "hidup", "kehidupan", "wisata", "liburan", "prank", "reaksi"],
}


def detect_genre(category_id: str, title: str) -> str:
    title_lower = title.lower()

    # Strong title signals always win (Indonesian creators often mis-categorise)
    # Check high-confidence genres first: Music, Food, Automotive, Sports, Gaming, Tech, DIY
    HIGH_CONFIDENCE = ["Music", "Food", "Automotive", "Sports", "Gaming", "Tech", "DIY"]
    for genre in HIGH_CONFIDENCE:
        keywords = TITLE_KEYWORDS.get(genre, [])
        if any(kw in title_lower for kw in keywords):
            return genre

    # Category map as secondary signal
    if category_id in CATEGORY_GENRE_MAP:
        return CATEGORY_GENRE_MAP[category_id]

    # Lifestyle keyword check last
    if any(kw in title_lower for kw in TITLE_KEYWORDS.get("Lifestyle", [])):
        return "Lifestyle"

    return "Lifestyle"


def calculate_viral_score(views: int, likes: int, position: int = 0) -> int:
    """
    Tuned for Indonesian YouTube trending (ID region).
    - Any video in the trending list starts with a base of 45 (YouTube already vouches for it).
    - Views tier adds up to 40 points, calibrated to ID content norms.
    - Engagement ratio adds up to 10 points.
    - Earlier trending position adds up to 5 bonus points.
    """
    base = 45

    # Views component — tiered for Indonesian market
    if views >= 10_000_000:
        views_score = 40
    elif views >= 5_000_000:
        views_score = 34
    elif views >= 2_000_000:
        views_score = 28
    elif views >= 1_000_000:
        views_score = 22
    elif views >= 500_000:
        views_score = 16
    elif views >= 200_000:
        views_score = 10
    elif views >= 50_000:
        views_score = 5
    else:
        views_score = 0

    # Engagement ratio component
    if views > 0 and likes > 0:
        ratio = likes / views
        if ratio >= 0.06:
            eng = 10
        elif ratio >= 0.04:
            eng = 8
        elif ratio >= 0.025:
            eng = 6
        elif ratio >= 0.015:
            eng = 4
        elif ratio >= 0.007:
            eng = 2
        else:
            eng = 1
    else:
        eng = 0   # likes disabled on this video

    # Earlier position in trending → slight bonus (up to 5 pts)
    pos_bonus = max(0, 5 - (position // 4))

    return min(100, max(1, base + views_score + eng + pos_bonus))


def get_recommended_duration(score: int) -> int:
    if score >= 85:
        return 30
    if score >= 70:
        return 60
    if score >= 55:
        return 90
    return 120


def format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fetch_trending(api_key: str, region: str = "ID", max_results: int = 20) -> list[dict]:
    params = {
        "part":       "snippet,statistics",
        "chart":      "mostPopular",
        "regionCode": region,
        "maxResults": max_results,
        "key":        api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=12)
    resp.raise_for_status()
    data = resp.json()

    videos = []
    for position, item in enumerate(data.get("items", [])):
        snippet = item.get("snippet", {})
        stats   = item.get("statistics", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        category_id = snippet.get("categoryId", "")
        title       = snippet.get("title", "")

        score    = calculate_viral_score(views, likes, position)
        genre    = detect_genre(category_id, title)
        duration = get_recommended_duration(score)

        thumbs    = snippet.get("thumbnails", {})
        thumbnail = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url", "")

        published_raw = snippet.get("publishedAt", "")
        published = published_raw[:10] if published_raw else "—"

        videos.append({
            "video_id":  item["id"],
            "title":     title,
            "channel":   snippet.get("channelTitle", ""),
            "thumbnail": thumbnail,
            "views":     format_count(views),
            "views_raw": views,
            "likes":     format_count(likes),
            "published": published,
            "genre":     genre,
            "score":     score,
            "duration":  duration,
        })

    videos.sort(key=lambda v: v["score"], reverse=True)
    return videos
