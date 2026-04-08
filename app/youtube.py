"""
YouTube API Integration — Upload Manager
OAuth2 + Video Upload + Thumbnail + Scheduling
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Scopes required
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# Quota costs
QUOTA_UPLOAD = 1600
QUOTA_THUMBNAIL = 50
QUOTA_DAILY_LIMIT = 10000


def get_client_config():
    """Get OAuth2 client config from environment variables"""
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8003/api/youtube/callback")],
        }
    }


def create_auth_flow(redirect_uri: str) -> Optional[Flow]:
    """Create OAuth2 flow for authorization"""
    config = get_client_config()
    if not config:
        return None
    flow = Flow.from_client_config(config, scopes=YOUTUBE_SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


def get_auth_url(redirect_uri: str, channel_id: int) -> Optional[str]:
    """Generate OAuth2 authorization URL"""
    flow = create_auth_flow(redirect_uri)
    if not flow:
        return None
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(channel_id),
    )
    return auth_url


def exchange_code(code: str, redirect_uri: str) -> Optional[dict]:
    """Exchange authorization code for tokens"""
    flow = create_auth_flow(redirect_uri)
    if not flow:
        return None
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
        "scopes": json.dumps(list(creds.scopes)) if creds.scopes else "[]",
    }


def build_credentials(token_data: dict) -> Credentials:
    """Build Credentials object from stored token data"""
    config = get_client_config()
    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config["web"]["client_id"] if config else "",
        client_secret=config["web"]["client_secret"] if config else "",
    )
    if token_data.get("token_expiry"):
        creds.expiry = datetime.fromisoformat(token_data["token_expiry"])
    return creds


def get_youtube_service(token_data: dict):
    """Build YouTube API service from stored tokens"""
    creds = build_credentials(token_data)
    # Auto-refresh if expired
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        # Return updated token info
        token_data["access_token"] = creds.token
        if creds.expiry:
            token_data["token_expiry"] = creds.expiry.isoformat()
        token_data["_refreshed"] = True
    return build("youtube", "v3", credentials=creds), token_data


def upload_video(
    token_data: dict,
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    category_id: int = 22,
    privacy: str = "private",
    publish_at: Optional[datetime] = None,
) -> dict:
    """
    Upload a video to YouTube.
    Returns: {"video_id": "...", "status": "uploaded", "quota_used": 1600, "token_data": {...}}
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    youtube, token_data = get_youtube_service(token_data)

    body = {
        "snippet": {
            "title": title[:100],  # YouTube max 100 chars
            "description": description[:5000],  # YouTube max 5000 chars
            "tags": (tags or [])[:500],  # YouTube max 500 tags
            "categoryId": str(category_id),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Scheduled publish
    if publish_at and privacy == "private":
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    media = MediaFileUpload(
        video_path,
        mimetype="video/*",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]
    return {
        "video_id": video_id,
        "status": "uploaded",
        "quota_used": QUOTA_UPLOAD,
        "token_data": token_data,
    }


def set_thumbnail(token_data: dict, video_id: str, thumbnail_path: str) -> dict:
    """Set custom thumbnail for a video"""
    if not os.path.exists(thumbnail_path):
        raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

    youtube, token_data = get_youtube_service(token_data)

    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=media,
    ).execute()

    return {
        "status": "thumbnail_set",
        "quota_used": QUOTA_THUMBNAIL,
        "token_data": token_data,
    }


def check_channel_auth(token_data: dict) -> dict:
    """Check if tokens are valid and get channel info"""
    try:
        youtube, token_data = get_youtube_service(token_data)
        response = youtube.channels().list(
            part="snippet",
            mine=True,
        ).execute()

        items = response.get("items", [])
        if not items:
            return {"valid": False, "error": "No channel found", "token_data": token_data}

        channel = items[0]
        return {
            "valid": True,
            "channel_title": channel["snippet"]["title"],
            "channel_id": channel["id"],
            "token_data": token_data,
        }
    except Exception as e:
        return {"valid": False, "error": str(e), "token_data": token_data}
