import hashlib
import base64
import os
import secrets
import requests
from youtube import fmt_collective, fmt_duration

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_URL = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"


def _client_key():
    key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    if not key:
        raise ValueError("TIKTOK_CLIENT_KEY is not set")
    return key


def _client_secret():
    key = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    if not key:
        raise ValueError("TIKTOK_CLIENT_SECRET is not set")
    return key


def generate_pkce():
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def build_auth_url(state, code_challenge, redirect_uri):
    params = (
        f"client_key={_client_key()}"
        f"&response_type=code"
        f"&scope=user.info.basic,video.list"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    return f"{AUTH_URL}?{params}"


def exchange_code(code, code_verifier, redirect_uri):
    resp = requests.post(TOKEN_URL, data={
        "client_key": _client_key(),
        "client_secret": _client_secret(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Token exchange failed: {data}")
    return data["access_token"]


def get_user_info(access_token):
    resp = requests.get(
        USER_URL,
        params={"fields": "open_id,display_name,avatar_url"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    user = data.get("data", {}).get("user", {})
    return {
        "display_name": user.get("display_name", "Unknown"),
        "avatar_url": user.get("avatar_url", ""),
    }


def get_videos(access_token, max_videos=50):
    videos = []
    cursor = None
    fields = "id,title,duration,view_count,like_count,create_time"

    while len(videos) < max_videos:
        body = {"max_count": min(20, max_videos - len(videos)), "fields": fields}
        if cursor:
            body["cursor"] = cursor

        resp = requests.post(
            VIDEO_LIST_URL,
            params={"fields": fields},
            json=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        for v in data.get("videos", []):
            duration_sec = int(v.get("duration", 0))
            views = int(v.get("view_count", 0))
            videos.append({
                "id": v.get("id", ""),
                "title": v.get("title") or v.get("video_description") or "(no title)",
                "published_at": str(v.get("create_time", ""))[:10],
                "duration_sec": duration_sec,
                "duration_fmt": fmt_duration(duration_sec),
                "views": views,
                "collective_sec": views * duration_sec,
            })

        if not data.get("has_more"):
            break
        cursor = data.get("cursor")

    return videos


def analyze_account(access_token):
    user = get_user_info(access_token)
    videos = get_videos(access_token, max_videos=50)

    for v in videos:
        v["collective_fmt"] = fmt_collective(v["collective_sec"])

    videos.sort(key=lambda v: v["collective_sec"], reverse=True)

    total_sec = sum(v["collective_sec"] for v in videos)
    total_views = sum(v["views"] for v in videos)

    return {
        "platform": "tiktok",
        "channel": {
            "title": user["display_name"],
            "thumbnail": user["avatar_url"],
            "subscriber_count": None,
        },
        "videos_analyzed": len(videos),
        "total_views": total_views,
        "total_collective": fmt_collective(total_sec),
        "top_videos": videos[:10],
    }
