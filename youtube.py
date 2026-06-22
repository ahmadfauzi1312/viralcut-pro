import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

CATEGORY_GENRE_MAP = {
    "1":  "Lifestyle", "2":  "Automotive", "10": "Music",
    "15": "Lifestyle", "17": "Sports",     "19": "Travel",
    "20": "Gaming",    "21": "Lifestyle",  "22": "Lifestyle",
    "23": "Comedy",    "24": "Entertainment", "25": "News",
    "26": "DIY",       "27": "Education",  "28": "Tech",
    "29": "Lifestyle",
}

TITLE_KEYWORDS = {
    "Automotive": ["car","truck","motor","bike","vehicle","engine","drift","racing",
                   "mobil","modif","otomotif","vespa","honda","toyota","suzuki","balap",
                   "ev","electric car","tesla","bbm","spbu","montir","bengkel"],
    "Food":       ["food","recipe","cooking","eat","restaurant","bake","chef","mukbang",
                   "masak","makan","resep","kuliner","makanan","minuman","kue","jajan",
                   "street food","warung","nasi","mie","bakso","soto","rendang","cobain"],
    "DIY":        ["diy","build","craft","woodwork","renovation","repair","how to",
                   "cara","buat","bikin","renovasi","dekorasi","kreasi","handmade","upcycle"],
    "Tech":       ["tech","phone","app","software","ai","gadget","coding","review",
                   "iphone","android","laptop","unboxing","setup","pc","komputer",
                   "chatgpt","robot","drone","samsung","xiaomi","artificial intelligence"],
    "Gaming":     ["game","gaming","play","minecraft","roblox","mobile legend","mlbb",
                   "ff","pubg","genshin","stream","esport","valorant","free fire",
                   "cod","ranked","tournament","gameplay","level","boss"],
    "Music":      ["music","song","official","mv","music video","lyric","cover",
                   "lagu","official video","single","album","konser","nyanyi","ost",
                   "dance practice","performance","kpop","pop","jazz","indie","rap"],
    "Sports":     ["sport","football","soccer","basket","badminton","tennis","race",
                   "bola","sepak bola","olahraga","tinju","atletik","juara",
                   "piala","liga","championship","olimpiade","asian games","sea games"],
    "Travel":     ["travel","wisata","liburan","trip","backpacker","explore","adventure",
                   "destinasi","pantai","gunung","bali","jakarta","yogyakarta","lombok",
                   "singapore","japan","korea","europe","hotel","resort","vlog perjalanan"],
    "Lifestyle":  ["vlog","day in","routine","fashion","style","tips","challenge",
                   "hidup","kehidupan","prank","reaksi","reaction","couple","family",
                   "morning","skincare","beauty","makeup","outfit","daily"],
    "Education":  ["belajar","edukasi","sekolah","kuliah","tips belajar","motivasi",
                   "inspirasi","sukses","bisnis","investasi","saham","crypto",
                   "learn","study","tutorial","how","apa itu","penjelasan","fakta"],
    "News":       ["berita","breaking news","update","terkini","viral","trending",
                   "politik","ekonomi","sosial","hukum","kriminal","bencana",
                   "news","report","press","terbaru","hari ini"],
    "Comedy":     ["comedy","funny","humor","parody","sketch","stand up",
                   "lucu","ngakak","kocak","gokil","receh","baper","absurd","meme"],
    "Entertainment": ["entertainment","celebrity","artis","drama","film","movie",
                      "series","netflix","sinetron","ftv","reality show","infotainment",
                      "trailer","teaser","behind the scenes"],
    "Podcast":    ["podcast","ngobrol","obrolan","diskusi","interview","wawancara",
                   "cerita","sharing","curhat","talkshow","talk show","conversation",
                   "episode","guest","host","insight","opinion","perspective"],
}

# YouTube category IDs to fetch per genre scan
GENRE_CATEGORY_IDS = {
    "Tech":          "28",
    "Gaming":        "20",
    "Music":         "10",
    "Sports":        "17",
    "Entertainment": "24",
    "Comedy":        "23",
    "Education":     "27",
    "News":          "25",
}

# Search queries for genres not covered by category IDs
GENRE_SEARCH_QUERIES = {
    "Automotive": ["otomotif mobil motor viral indonesia", "review mobil motor terbaru"],
    "Food":       ["kuliner viral indonesia terbaru", "masak resep mudah enak"],
    "DIY":        ["diy kreasi viral indonesia", "cara membuat sendiri tutorial"],
    "Travel":     ["wisata indonesia viral terbaru", "liburan explore destinasi"],
    "Lifestyle":  ["vlog kehidupan viral indonesia", "tips lifestyle indonesia"],
    "Podcast":    ["podcast indonesia terbaru informatif", "wawancara inspiratif talkshow"],
}


def detect_genre(category_id: str, title: str) -> str:
    title_lower = title.lower()
    HIGH_CONFIDENCE = ["Music","Food","Automotive","Sports","Gaming","Tech","DIY",
                       "Travel","Podcast","Comedy","News","Education","Entertainment"]
    for genre in HIGH_CONFIDENCE:
        if any(kw in title_lower for kw in TITLE_KEYWORDS.get(genre, [])):
            return genre
    if category_id in CATEGORY_GENRE_MAP:
        return CATEGORY_GENRE_MAP[category_id]
    if any(kw in title_lower for kw in TITLE_KEYWORDS.get("Lifestyle", [])):
        return "Lifestyle"
    return "Lifestyle"


def calculate_viral_score(views: int, likes: int, position: int = 0) -> int:
    base = 45
    if views >= 10_000_000:   views_score = 40
    elif views >= 5_000_000:  views_score = 34
    elif views >= 2_000_000:  views_score = 28
    elif views >= 1_000_000:  views_score = 22
    elif views >= 500_000:    views_score = 16
    elif views >= 200_000:    views_score = 10
    elif views >= 50_000:     views_score = 5
    else:                     views_score = 0

    if views > 0 and likes > 0:
        ratio = likes / views
        if ratio >= 0.06:   eng = 10
        elif ratio >= 0.04: eng = 8
        elif ratio >= 0.025:eng = 6
        elif ratio >= 0.015:eng = 4
        elif ratio >= 0.007:eng = 2
        else:               eng = 1
    else:
        eng = 0

    pos_bonus = max(0, 5 - (position // 4))
    return min(100, max(1, base + views_score + eng + pos_bonus))


def get_recommended_duration(score: int) -> int:
    if score >= 85: return 30
    if score >= 70: return 60
    if score >= 55: return 90
    return 120


def format_count(n: int) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(n)


def _parse_video_item(item, position=0, force_genre=None):
    snippet = item.get("snippet", {})
    stats   = item.get("statistics", {})
    views   = int(stats.get("viewCount", 0))
    likes   = int(stats.get("likeCount", 0))
    title   = snippet.get("title", "")
    cat_id  = snippet.get("categoryId", "")
    score   = calculate_viral_score(views, likes, position)
    genre   = force_genre or detect_genre(cat_id, title)
    thumbs  = snippet.get("thumbnails", {})
    thumb   = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url", "")
    pub     = snippet.get("publishedAt", "")[:10]
    return {
        "video_id":  item["id"] if isinstance(item["id"], str) else item["id"].get("videoId",""),
        "title":     title,
        "channel":   snippet.get("channelTitle", ""),
        "thumbnail": thumb,
        "views":     format_count(views),
        "views_raw": views,
        "likes":     format_count(likes),
        "published": pub,
        "genre":     genre,
        "score":     score,
        "duration":  get_recommended_duration(score),
        "source":    "youtube",
    }


def fetch_trending(api_key: str, region: str = "ID", max_results: int = 50) -> list:
    """Fetch most popular videos in region."""
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
    videos = [_parse_video_item(item, i) for i, item in enumerate(data.get("items", []))]
    videos.sort(key=lambda v: v["score"], reverse=True)
    return videos


def fetch_by_category(api_key: str, region: str = "ID") -> list:
    """Fetch trending videos per YouTube category for more genre variety."""
    all_videos = []
    seen_ids = set()

    for genre, cat_id in GENRE_CATEGORY_IDS.items():
        try:
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region,
                "videoCategoryId": cat_id,
                "maxResults": 10,
                "key": api_key,
            }
            resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for i, item in enumerate(data.get("items", [])):
                vid_id = item.get("id", "")
                if vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    all_videos.append(_parse_video_item(item, i, force_genre=genre))
        except Exception:
            continue

    return all_videos


def fetch_by_search(api_key: str, region: str = "ID") -> list:
    """Fetch videos via search queries for genres not in category map."""
    all_videos = []
    seen_ids = set()

    for genre, queries in GENRE_SEARCH_QUERIES.items():
        for query in queries[:1]:  # 1 query per genre to save quota
            try:
                # Search
                search_params = {
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "order": "viewCount",
                    "regionCode": region,
                    "maxResults": 5,
                    "key": api_key,
                }
                resp = requests.get(f"{YOUTUBE_API_BASE}/search", params=search_params, timeout=10)
                if resp.status_code != 200:
                    continue
                search_data = resp.json()
                video_ids = [
                    item["id"]["videoId"]
                    for item in search_data.get("items", [])
                    if item.get("id", {}).get("videoId") and item["id"]["videoId"] not in seen_ids
                ]
                if not video_ids:
                    continue

                # Get stats
                stats_params = {
                    "part": "snippet,statistics",
                    "id": ",".join(video_ids),
                    "key": api_key,
                }
                stats_resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=stats_params, timeout=10)
                if stats_resp.status_code != 200:
                    continue
                stats_data = stats_resp.json()
                for i, item in enumerate(stats_data.get("items", [])):
                    vid_id = item.get("id", "")
                    if vid_id not in seen_ids:
                        seen_ids.add(vid_id)
                        all_videos.append(_parse_video_item(item, i, force_genre=genre))
            except Exception:
                continue

    return all_videos


def fetch_podcasts(api_key: str, region: str = "ID") -> list:
    """Fetch informative podcast/talkshow content."""
    queries = [
        "podcast indonesia terbaru informatif",
        "wawancara inspiratif indonesia 2024",
        "talkshow diskusi bisnis investasi",
    ]
    all_videos = []
    seen_ids = set()

    for query in queries:
        try:
            search_params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "videoDuration": "long",
                "order": "viewCount",
                "regionCode": region,
                "maxResults": 5,
                "key": api_key,
            }
            resp = requests.get(f"{YOUTUBE_API_BASE}/search", params=search_params, timeout=10)
            if resp.status_code != 200:
                continue
            video_ids = [
                item["id"]["videoId"]
                for item in resp.json().get("items", [])
                if item.get("id", {}).get("videoId") and item["id"]["videoId"] not in seen_ids
            ]
            if not video_ids:
                continue

            stats_resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params={
                "part": "snippet,statistics",
                "id": ",".join(video_ids),
                "key": api_key,
            }, timeout=10)
            if stats_resp.status_code != 200:
                continue

            for i, item in enumerate(stats_resp.json().get("items", [])):
                vid_id = item.get("id", "")
                if vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    v = _parse_video_item(item, i, force_genre="Podcast")
                    v["duration"] = 120
                    all_videos.append(v)
        except Exception:
            continue

    return all_videos


def fetch_all_sources(api_key: str, region: str = "ID", min_score: int = 45) -> list:
    """
    Aggregate from all sources:
    1. General trending (mostPopular)
    2. Per-category trending
    3. Search-based (genre queries)
    4. Podcasts
    Deduplicate and sort by viral score.
    """
    all_videos = []
    seen_ids = set()

    # Source 1: general trending
    try:
        for v in fetch_trending(api_key, region, max_results=50):
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
    except Exception:
        pass

    # Source 2: per-category
    try:
        for v in fetch_by_category(api_key, region):
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
    except Exception:
        pass

    # Source 3: search-based genres
    try:
        for v in fetch_by_search(api_key, region):
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
    except Exception:
        pass

    # Source 4: podcasts
    try:
        for v in fetch_podcasts(api_key, region):
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
    except Exception:
        pass

    # Filter and sort
    result = [v for v in all_videos if v["score"] >= min_score]
    result.sort(key=lambda v: v["score"], reverse=True)
    return result
ENDOFFILE
echo "Done"
python3 -c "import ast; ast.parse(open('/mnt/user-data/outputs/youtube.py').read()); print('Syntax OK! Lines:', len(open('/mnt/user-data/outputs/youtube.py').readlines()))"
