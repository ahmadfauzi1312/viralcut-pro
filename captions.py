import random

GENRE_HOOKS = {
    "Automotive": [
        "This car hack will blow your mind 🚗💨",
        "Wait until you see what happens when I tried this on my car...",
        "Car owners — you NEED to know this right now 🔥",
        "I can't believe I drove without knowing this for years",
    ],
    "Food": [
        "I can't believe this recipe only takes 10 minutes 🍽️",
        "This is the best thing I've ever eaten — and it's SO easy",
        "Stop scrolling, you need to try this recipe 🤌",
        "3 ingredients. 5 minutes. Life-changing flavour",
    ],
    "DIY": [
        "I built this in one weekend and saved $500 🔨",
        "This DIY trick will save you SO much money",
        "Transform your space with this easy hack ✨",
        "No experience needed — anyone can do this",
    ],
    "Tech": [
        "This hidden feature will change how you use your phone 📱",
        "Nobody talks about this tech trick — until now",
        "This will make you 10× more productive in minutes 💻",
        "I've been using this wrong for years and I just found out",
    ],
    "Lifestyle": [
        "This one habit changed my entire life 💪",
        "I wish I knew this sooner — it's life-changing",
        "Stop wasting time — try this instead ⚡",
        "The secret nobody tells you about living better",
    ],
    "Gaming": [
        "This strategy made me rank #1 overnight 🎮",
        "Nobody uses this trick — that's why I'm winning",
        "Game-changing tip that pros don't want you to know 🏆",
        "I went from silver to diamond using this ONE trick",
    ],
    "Sports": [
        "This training hack improved my performance by 200% 💪",
        "The secret technique pros use but never teach",
        "This changed my game completely 🏅",
        "I trained like this for 30 days and here's what happened",
    ],
    "Music": [
        "This music trick will give you chills every time 🎵",
        "I can't stop listening to this — and neither will you",
        "The song that broke the internet — here's why 🎶",
    ],
}

GENRE_HASHTAGS = {
    "Automotive": ["#cars", "#automotive", "#carlovers", "#carmod", "#drivinglife", "#carenthusiast", "#motoring", "#carsoftiktok"],
    "Food":       ["#foodie", "#recipe", "#cooking", "#foodlover", "#delicious", "#easyrecipe", "#foodtok", "#homecooking"],
    "DIY":        ["#diy", "#homeimprovement", "#lifehack", "#tutorial", "#crafts", "#diyhome", "#makeit", "#handmade"],
    "Tech":       ["#tech", "#technology", "#gadgets", "#techlife", "#iphone", "#productivity", "#techtips", "#techreview"],
    "Lifestyle":  ["#lifestyle", "#motivation", "#tips", "#selfimprovement", "#daily", "#mindset", "#livingmybest", "#lifeadvice"],
    "Gaming":     ["#gaming", "#gamer", "#gameplay", "#gaminglife", "#esports", "#streamer", "#gamers", "#gamingtips"],
    "Sports":     ["#sports", "#fitness", "#athlete", "#training", "#workout", "#sportslife", "#champion", "#fitnessmotivation"],
    "Music":      ["#music", "#musiclover", "#song", "#viral", "#trending", "#musicvideo", "#nowplaying", "#banger"],
}

CTAS = [
    "Follow for more viral content! 🔥",
    "Save this before it's gone! 🔖",
    "Share with a friend who needs to see this!",
    "Drop a 🔥 if this helped you!",
    "Try this yourself and comment below!",
    "Follow for daily viral content 👀",
    "Like if you learned something new! ✅",
]

FORMAT_CAPTION_STYLES = {
    "portrait": {
        "label": "TikTok / Reels style",
        "tip":   "Short punchy hook in the first line. Use line breaks for rhythm. End with a question to boost comments.",
        "icon":  "📱",
    },
    "landscape": {
        "label": "YouTube style",
        "tip":   "Descriptive title-style opening. Include keywords in the first 125 characters for SEO. End with 'Watch till the end!'",
        "icon":  "🖥",
    },
    "square": {
        "label": "Instagram Feed style",
        "tip":   "Lead with an emoji. Keep it conversational. Use 3–5 hashtags at the end.",
        "icon":  "📷",
    },
}


def _hashtags(genre: str, n: int) -> str:
    pool = GENRE_HASHTAGS.get(genre, GENRE_HASHTAGS["Lifestyle"])
    chosen = random.sample(pool, min(n, len(pool)))
    return " ".join(chosen)


def _hook(genre: str) -> str:
    hooks = GENRE_HOOKS.get(genre, GENRE_HOOKS["Lifestyle"])
    return random.choice(hooks)


def _cta() -> str:
    return random.choice(CTAS)


def generate(title: str, genre: str, channel: str, score: int) -> dict:
    hook = _hook(genre)
    cta  = _cta()

    short = f"{hook} {_hashtags(genre, 3)}"

    medium = (
        f"{hook}\n\n"
        f"This video from {channel} is going viral right now — "
        f"and it's easy to see why. Pure {genre.lower()} gold with a viral score of {score}/100.\n\n"
        f"{cta} {_hashtags(genre, 4)}"
    )

    long = (
        f"{hook}\n\n"
        f"✅ Why this is blowing up:\n"
        f"📌 Topic: {title}\n"
        f"📌 Creator: {channel}\n"
        f"📌 Viral Score: {score}/100\n\n"
        f"Content like this in the {genre} niche is performing exceptionally well right now — "
        f"engagement rates are through the roof and the algorithm is actively pushing it.\n\n"
        f"If you're in the {genre} space, this is exactly the style and format you should be studying "
        f"and adapting for your own channel.\n\n"
        f"👉 {cta}\n\n"
        f"{_hashtags(genre, 5)} #viral #trending #viralcontent"
    )

    return {
        "short":  short,
        "medium": medium,
        "long":   long,
    }
