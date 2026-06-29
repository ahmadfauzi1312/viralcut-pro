import os
import json
import requests
import time

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def get_oauth_credentials(db_settings: dict) -> dict:
    """Get client_id and client_secret from settings."""
    return {
        "client_id": db_settings.get("oauth_youtube_client_id", ""),
        "client_secret": db_settings.get("oauth_youtube_client_secret", ""),
    }


def exchange_code_for_token(code: str, client_id: str, client_secret: str,
                             redirect_uri: str) -> dict:
    """Exchange authorization code for access + refresh token."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str, client_id: str,
                          client_secret: str) -> dict:
    """Use refresh token to get new access token."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_valid_access_token(settings: dict, redirect_uri: str) -> str:
    """
    Get a valid access token, refreshing if needed.
    Raises ValueError if not configured.
    """
    creds = get_oauth_credentials(settings)
    if not creds["client_id"] or not creds["client_secret"]:
        raise ValueError("YouTube OAuth credentials not configured.")

    token_data_raw = settings.get("oauth_youtube_token_data", "")
    access_token = settings.get("oauth_youtube_access_token", "")

    # If we have token_data (JSON with refresh_token), use that
    if token_data_raw and token_data_raw.startswith("{"):
        try:
            token_data = json.loads(token_data_raw)
            refresh_token = token_data.get("refresh_token", "")
            if refresh_token:
                new_tokens = refresh_access_token(
                    refresh_token,
                    creds["client_id"],
                    creds["client_secret"]
                )
                return new_tokens["access_token"]
        except Exception:
            pass

    # If we have a code: prefix, need to exchange
    if access_token.startswith("code:"):
        code = access_token[5:]
        token_data = exchange_code_for_token(
            code, creds["client_id"], creds["client_secret"], redirect_uri
        )
        return token_data.get("access_token", ""), token_data

    if access_token and not access_token.startswith("code:"):
        return access_token

    raise ValueError("No valid YouTube token. Please reconnect your YouTube account.")


def upload_video_to_youtube(
    access_token: str,
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    category_id: str = "22",
    privacy: str = "public",
    made_for_kids: bool = False,
) -> dict:
    """
    Upload a video file to YouTube.
    Returns the uploaded video's data including id and url.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    file_size = os.path.getsize(video_path)

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or ["viral", "trending", "shorts"],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": made_for_kids,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    # Step 1: Initiate resumable upload
    init_resp = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
            "X-Upload-Content-Length": str(file_size),
        },
        json=metadata,
        timeout=30,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise ValueError("No upload URL returned from YouTube")

    # Step 2: Upload the video file
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/*",
                "Content-Length": str(file_size),
            },
            data=f,
            timeout=300,
        )
    upload_resp.raise_for_status()
    video_data = upload_resp.json()

    video_id = video_data.get("id", "")
    return {
        "ok": True,
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "title": title,
        "status": video_data.get("status", {}).get("uploadStatus", "uploaded"),
    }


def get_channel_info(access_token: str) -> dict:
    """Get info about the connected YouTube channel."""
    resp = requests.get(
        f"{YOUTUBE_API_BASE}/channels",
        params={"part": "snippet,statistics", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    if not items:
        return {}
    item = items[0]
    return {
        "channel_id": item["id"],
        "title": item["snippet"]["title"],
        "subscribers": item["statistics"].get("subscriberCount", "0"),
        "thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
    }
