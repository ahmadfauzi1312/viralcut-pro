import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

CATEGORY_GENRE_MAP = {
    "1":  "Lifestyle",
    "2":  "Automotive",
    "10": "Music",
    "15": "Lifestyle",
    "17": "Sports",
    "19": "Travel",
    "20": "Gaming",
    "21": "Lifestyle",
    "22": "Lifestyle",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News",
    "26": "DIY",
    "27": "Education",
    "28": "Tech",
    "29": "Lifestyle",
}

TITLE_KEYWORDS = {
    "Automotive": ["car", "truck", "motor", "bike", "vehicle", "engine", "drift", "racing",
                   "mobil", "modif", "otomotif", "vespa", "honda", "toyota", "suzuki", "balap",
                   "ev", "electric car", "tesla", "spbu", "bensin", "bbm"],
    "Food": ["food", "recipe", "cooking", "eat", "restaurant", "bake", "chef", "mukbang",
             "masak", "makan", "resep", "kuliner", "makanan", "minuman", "kue", "jajan",
             "street food", "warung", "nasi", "mie", "bakso", "soto", "rendang"],
    "DIY": ["diy", "build", "craft", "woodwork", "renovation", "repair", "tutorial", "how to",
            "cara", "buat", "bikin", "renovasi", "dekorasi", "kreasi", "handmade", "upcycle"],
    "Tech": ["tech", "phone", "app", "software", "ai", "gadget", "coding", "review",
             "iphone", "android", "laptop", "unboxing", "setup", "pc", "komputer",
             "chatgpt", "artificial intelligence", "robot", "drone", "samsung", "xiaomi"],
    "Gaming": ["game", "gaming", "play", "minecraft", "roblox", "mobile legend", "mlbb",
               "ff", "pubg", "genshin", "stream", "esport", "valorant", "lego",
               "free fire", "cod", "call of duty", "ranked", "tournament"],
    "Music": ["music", "song", "official", "mv", "music video", "lyric", "cover",
              "lagu", "official video", "single", "album", "konser", "nyanyi", "ost",
              "dance practice", "performance", "kpop", "pop", "jazz", "indie"],
    "Sports": ["sport", "football", "soccer", "basket", "badminton", "tennis", "race",
               "bola", "sepak bola", "olahraga", "tinju", "atletik", "juara",
               "piala", "liga", "championship", "olimpiade", "asian games", "sea games"],
    "Lifestyle": ["vlog", "day in", "routine", "fashion", "style", "tips", "challenge",
                  "hidup", "kehidupan", "prank", "reaksi", "reaction", "couple", "family",
                  "morning", "night", "skincare", "beauty", "makeup", "outfit"],
    "Travel": ["travel", "wisata", "liburan", "trip", "backpacker", "explore", "adventure",
               "destinasi", "pantai", "gunung", "bali", "jakarta", "yogyakarta", "lombok",
               "singapore", "japan", "korea", "europe", "hotel", "resort"],
    "Education": ["belajar", "edukasi", "sekolah", "kuliah", "tips belajar", "motivasi",
                  "inspirasi", "sukses", "bisnis", "investasi", "saham", "crypto",
                  "learn", "study", "education", "school", "university", "tutorial"],
    "News": ["berita", "breaking news", "update", "terkini", "viral", "trending",
             "politik", "ekonomi", "sosial", "hukum", "kriminal", "bencana",
             "news", "report", "press", "journalist"],
    "Comedy": ["comedy", "funny", "humor", "parody", "sketch", "stand up",
               "lucu", "ngakak", "kocak", "gokil", "receh", "baper", "absurd"],
    "Entertainment": ["entertainment", "celebrity", "artis", "drama", "film", "movie",
                      "series", "netflix", "sinetron", "ftv", "reality show", "infotainment"],
    "Podcast": ["podcast", "ngobrol", "obrolan", "diskusi", "interview", "wawancara",
                "cerita", "sharing", "curhat", "talkshow", "talk show", "conversation",
                "episode", "guest", "host", "insight", "opinion", "perspective"],
}


def detect_genre(category_id: str, title: str) -> str:
    title_lower = title.lower()
    HIGH_CONFIDENCE = ["Music", "Food", "Automotive", "Sports", "Gaming", "Tech", "DIY",
                       "Travel", "Podcast", "Comedy", "News", "Education", "Entertainment"]
    for genre in HIGH_CONFIDENCE:
        keywords = TITLE_KEYWORDS.get(genre, [])
        if any(kw in title_lower for kw in keywords):
            return genre
    if category_id in CATEGORY_GENRE_MAP:
        return CATEGORY_GENRE_MAP[category_id]
    if any(kw in title_lower for kw in TITLE_KEYWORDS.get("Lifestyle", [])):
        return "Lifestyle"
    return "Lifestyle"


def calculate_viral_score(views: int, likes: int, position: int = 0) -> int:
    base = 45
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
        eng = 0

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


def fetch_trending(api_key: str, region: str = "ID", max_results: int = 20) -> list:
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=12)
    resp.raise_for_status()
    data = resp.json()

    videos = []
    for position, item in enumerate(data.get("items", [])):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        category_id = snippet.get("categoryId", "")
        title = snippet.get("title", "")

        score = calculate_viral_score(views, likes, position)
        genre = detect_genre(category_id, title)
        duration = get_recommended_duration(score)

        thumbs = snippet.get("thumbnails", {})
        thumbnail = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url", "")

        published_raw = snippet.get("publishedAt", "")
        published = published_raw[:10] if published_raw else ""

        videos.append({
            "video_id": item["id"],
            "title": title,
            "channel": snippet.get("channelTitle", ""),
            "thumbnail": thumbnail,
            "views": format_count(views),
            "views_raw": views,
            "likes": format_count(likes),
            "published": published,
            "genre": genre,
            "score": score,
            "duration": duration,
            "source": "youtube",
        })

    videos.sort(key=lambda v: v["score"], reverse=True)
    return videos


def fetch_podcasts(api_key: str, region: str = "ID", max_results: int = 10) -> list:
    """Fetch informative/podcast content from YouTube search."""
    search_queries = [
        "podcast indonesia terbaru informatif",
        "wawancara inspiratif indonesia",
        "diskusi bisnis investasi indonesia",
        "edukasi motivasi sukses",
        "talk show terbaru indonesia",
    ]

    all_video_ids = []
    for query in search_queries[:2]:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoDuration": "long",
            "order": "viewCount",
            "regionCode": region,
            "maxResults": 5,
            "key": api_key,
        }
        try:
            resp = requests.get(f"{YOUTUBE_API_BASE}/search", params=params, timeout=12)
            resp.raise_for_status()
            data = resp.json()
            ids = [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]
            all_video_ids.extend(ids)
        except Exception:
            continue

    if not all_video_ids:
        return []

    unique_ids = list(dict.fromkeys(all_video_ids))[:max_results]
    params = {
        "part": "snippet,statistics",
        "id": ",".join(unique_ids),
        "key": api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=12)
    resp.raise_for_status()
    data = resp.json()

    videos = []
    for position, item in enumerate(data.get("items", [])):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        title = snippet.get("title", "")

        score = calculate_viral_score(views, likes, position)
        duration = 120

        thumbs = snippet.get("thumbnails", {})
        thumbnail = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url", "")

        published_raw = snippet.get("publishedAt", "")
        published = published_raw[:10] if published_raw else ""

        videos.append({
            "video_id": item["id"],
            "title": title,
            "channel": snippet.get("channelTitle", ""),
            "thumbnail": thumbnail,
            "views": format_count(views),
            "views_raw": views,
            "likes": format_count(likes),
            "published": published,
            "genre": "Podcast",
            "score": score,
            "duration": duration,
            "source": "podcast",
        })

    videos.sort(key=lambda v: v["score"], reverse=True)
    return videos
