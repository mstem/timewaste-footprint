import re
import requests
import os

BASE_URL = "https://www.googleapis.com/youtube/v3"
SECONDS_PER_YEAR = 365.25 * 24 * 3600
SECONDS_PER_MONTH = SECONDS_PER_YEAR / 12
SECONDS_PER_LIFETIME = 70 * SECONDS_PER_YEAR


def _api_key():
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise ValueError("YOUTUBE_API_KEY is not set")
    return key


def _get(endpoint, **params):
    params["key"] = _api_key()
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=10)
    if resp.status_code == 403:
        raise PermissionError("API quota exceeded or key invalid")
    resp.raise_for_status()
    return resp.json()


def parse_duration(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s


def get_channel_info(handle):
    handle = handle.lstrip("@")
    data = _get(
        "channels",
        part="snippet,statistics,contentDetails",
        forHandle=handle,
    )
    items = data.get("items", [])
    if not items:
        raise LookupError(f"No channel found for @{handle}")
    item = items[0]
    return {
        "id": item["id"],
        "title": item["snippet"]["title"],
        "thumbnail": (
            item["snippet"]["thumbnails"].get("medium")
            or item["snippet"]["thumbnails"].get("default")
            or {}
        ).get("url", ""),
        "subscriber_count": int(item["statistics"].get("subscriberCount", 0)),
        "video_count": int(item["statistics"].get("videoCount", 0)),
        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def get_video_ids(uploads_playlist_id, max_videos=50):
    ids = []
    page_token = None
    while len(ids) < max_videos:
        batch = min(50, max_videos - len(ids))
        params = dict(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=batch,
        )
        if page_token:
            params["pageToken"] = page_token
        data = _get("playlistItems", **params)
        for item in data.get("items", []):
            ids.append(item["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


def get_video_details(video_ids):
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        data = _get(
            "videos",
            part="snippet,contentDetails,statistics",
            id=",".join(batch),
        )
        for item in data.get("items", []):
            duration_sec = parse_duration(item["contentDetails"].get("duration", ""))
            views = int(item["statistics"].get("viewCount", 0))
            videos.append(
                {
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"][:10],
                    "duration_sec": duration_sec,
                    "views": views,
                    "collective_sec": views * duration_sec,
                }
            )
    return videos


def fmt_duration(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def fmt_collective(total_sec):
    hours = total_sec / 3600
    days = total_sec / 86400
    months = total_sec / SECONDS_PER_MONTH
    years = total_sec / SECONDS_PER_YEAR
    lifetimes = total_sec / SECONDS_PER_LIFETIME

    if years >= 1:
        primary = f"{years:,.1f} yrs"
    elif months >= 1:
        primary = f"{months:,.1f} months"
    elif days >= 1:
        primary = f"{days:,.1f} days"
    elif hours >= 1:
        primary = f"{hours:,.1f} hrs"
    else:
        primary = f"{total_sec / 60:,.0f} min"

    return {
        "hours": f"{hours:,.0f}",
        "years": f"{years:,.1f}",
        "lifetimes": f"{lifetimes:,.2f}",
        "primary": primary,
    }


def analyze_channel(handle, max_videos=50):
    channel = get_channel_info(handle)
    video_ids = get_video_ids(channel["uploads_playlist_id"], max_videos=max_videos)
    videos = get_video_details(video_ids)

    for v in videos:
        v["duration_fmt"] = fmt_duration(v["duration_sec"])
        v["collective_fmt"] = fmt_collective(v["collective_sec"])

    videos.sort(key=lambda v: v["collective_sec"], reverse=True)

    total_sec = sum(v["collective_sec"] for v in videos)
    total_views = sum(v["views"] for v in videos)

    return {
        "channel": channel,
        "videos_analyzed": len(videos),
        "total_views": total_views,
        "total_collective": fmt_collective(total_sec),
        "top_videos": videos[:10],
    }
