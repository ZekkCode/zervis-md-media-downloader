import asyncio
import logging
import os
import re
import json
import secrets
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
import uvicorn
import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from scripts.shared import (
    BASE_DIR,
    LOG_DIR,
    COOKIES_DIR,
    COOKIE_PLATFORM_FILES,
    CACHE_DB,
    TOPICS_FILE,
    CLEANUP_FILE,
    db_connect,
    init_all_db,
    load_cleanup_settings,
    is_cleanup_enabled,
    cleanup_key,
    get_cache,
    save_cache,
    record_bot_cleanup_message,
    mark_cleanup_message_deleted,
    platform_key_from_url,
    get_cookie_file,
    validate_cookie_text,
    load_topics,
    get_topic_name,
    extract_user_tags,
    site_name_from_url,
    media_id_from_url,
)

ENV_PATH = BASE_DIR / ".env"

# Tagger paths – configurable via .env, falls back to system python3
TAGGER_PYTHON_RAW = os.getenv("TAGGER_PYTHON", "python3")
TAGGER_PYTHON = Path(TAGGER_PYTHON_RAW) if TAGGER_PYTHON_RAW else Path("python3")
TAGGER_SCRIPT = BASE_DIR / "video_tagger" / "tag_video.py"
TAGGER_TIMEOUT_SECONDS = 25
DEFAULT_ADULT_TAGS = [
    "#adult",
    "#nsfw",
    "#18plus",
    "#montok",
    "#semok",
    "#seksi",
    "#spicy",
    "#nakal",
    "#lokal",
    "#indonesia",
    "#susu_gede",
    "#bokong_besar",
    "#dada_besar",
    "#paha_mulus",
    "#body_semok",
    "#bigboobs",
    "#booty",
    "#hotclip",
]

load_dotenv(ENV_PATH)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
X_WEB_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
X_TWEET_RESULT_QUERY_ID = "8CEYnZhCp0dx9DFyyEBlbQ"
COOKIE_FILES = {
    "default": os.getenv("COOKIES_FILE"),
    "x": os.getenv("X_COOKIES_FILE"),
    "instagram": os.getenv("INSTAGRAM_COOKIES_FILE"),
    "tiktok": os.getenv("TIKTOK_COOKIES_FILE"),
    "youtube": os.getenv("YOUTUBE_COOKIES_FILE"),
    "facebook": os.getenv("FACEBOOK_COOKIES_FILE"),
}

DOWNLOAD_DIR = BASE_DIR / "downloads"
WORK_QUEUE: asyncio.Queue = asyncio.Queue()

# === Dashboard config ===
WORKER_HOST = os.getenv("WORKER_HOST", "127.0.0.1")
WORKER_PORT = int(os.getenv("WORKER_PORT", "3000"))
DASHBOARD_TOKEN_FILE = LOG_DIR / "dashboard_token.txt"


def get_dashboard_token() -> str:
    """Token cuma aktif kalau diset di .env. Kosong = dashboard tanpa token (akses lokal)."""
    return os.getenv("DASHBOARD_TOKEN") or ""


DASHBOARD_TOKEN = get_dashboard_token()

DASHBOARD_DIR = Path(__file__).resolve().parent
DASHBOARD_HTML_FILE = DASHBOARD_DIR / "dashboard.html"
DASHBOARD_JS_FILE = DASHBOARD_DIR / "dashboard.js"


def read_dashboard_asset(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback

app = FastAPI()

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "worker.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("telegram-x-video-worker")
logging.getLogger("httpx").setLevel(logging.WARNING)


class TwitterVideoRequest(BaseModel):
    chat_id: int
    group_name: Optional[str] = None
    message_thread_id: Optional[int] = None
    tweet_id: str
    original_url: str
    user_tags: Optional[list[str]] = None


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip()
    return name or "Unknown"


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        return ""

    tag = tag if tag.startswith("#") else f"#{tag}"
    return re.sub(r"[^\w#]", "_", tag)


def enrich_adult_tags(
    tags: list[str],
    topic_name: str = "",
    user_tags: Optional[list[str]] = None,
) -> list[str]:
    """Pastikan caption adult tidak jatuh ke satu tag generic saja."""
    merged: list[str] = []

    for tag in (user_tags or []) + tags:
        if not tag:
            continue
        normalized = normalize_tag(tag)
        if normalized not in merged and normalized != "#blocked":
            merged.append(normalized)

    topic = topic_name.lower()
    topic_tags = []
    if "asia" in topic:
        topic_tags.extend(["#asian", "#seksi", "#mulus"])
    if "indian" in topic:
        topic_tags.extend(["#indian", "#seksi", "#semok"])
    if "pmv" in topic:
        topic_tags.extend(["#pmv", "#compilation", "#shortclip"])
    if "fantasy" in topic:
        topic_tags.extend(["#fantasy", "#cosplay", "#fetish"])

    for tag in topic_tags + DEFAULT_ADULT_TAGS:
        if tag not in merged:
            merged.append(tag)

    return merged[:10]


def get_save_folder(group_name: str, topic_name: str) -> Path:
    folder = DOWNLOAD_DIR / safe_name(group_name) / safe_name(topic_name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def next_file_index(folder: Path, topic_name: str) -> int:
    base_name = safe_name(topic_name)
    pattern = re.compile(rf"^{re.escape(base_name)}-(\d+)\.")
    highest = 0

    for path in folder.iterdir():
        if not path.is_file():
            continue

        match = pattern.match(path.name)
        if not match:
            continue

        highest = max(highest, int(match.group(1)))

    return highest + 1


def build_save_path(group_name: str, topic_name: str, extension: str) -> Path:
    folder = get_save_folder(group_name, topic_name)
    index = next_file_index(folder, topic_name)
    extension = extension if extension.startswith(".") else f".{extension}"
    return folder / f"{safe_name(topic_name)}-{index}{extension}"


def encode_cache_items(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


def decode_cache_items(value: Optional[str]) -> list[str]:
    if not value:
        return []

    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data if item]
    except Exception:
        pass

    return [value]


def telegram_media_kind(file_path_or_id: str) -> str:
    extension = Path(file_path_or_id).suffix.lower()
    video_extensions = {".mp4", ".m4v", ".mov"}
    photo_extensions = {".jpg", ".jpeg", ".png"}

    if extension in video_extensions or not extension:
        return "video"
    if extension in photo_extensions:
        return "photo"
    return "document"


def is_local_video_file(file_path_or_id: str) -> bool:
    return os.path.isfile(file_path_or_id) and telegram_media_kind(file_path_or_id) == "video"


def is_downloaded_media_file(path: Path) -> bool:
    if not path.is_file():
        return False

    suffixes = [suffix.lower() for suffix in path.suffixes]
    if any(suffix in {".part", ".ytdl", ".tmp"} for suffix in suffixes):
        return False

    return path.suffix.lower() in {
        ".mp4",
        ".m4v",
        ".mov",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
    }


def pick_best_video(media: dict) -> Optional[str]:
    variants = media.get("variants", [])
    mp4s = [
        variant
        for variant in variants
        if variant.get("content_type") == "video/mp4" and variant.get("url")
    ]

    if not mp4s:
        return None

    best = max(mp4s, key=lambda variant: variant.get("bit_rate", 0))
    return best["url"]


def summarize_x_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text[:220]

    if isinstance(data, dict):
        errors = data.get("errors")
        if errors and isinstance(errors, list):
            first_error = errors[0]
            if isinstance(first_error, dict):
                return (
                    first_error.get("message")
                    or first_error.get("detail")
                    or str(first_error)
                )[:220]

        detail = data.get("detail") or data.get("title")
        if detail:
            return str(detail)[:220]

    return str(data)[:220]


async def get_media_urls_from_x(tweet_id: str) -> dict:
    if not X_BEARER_TOKEN:
        return {
            "ok": False,
            "media": [],
            "reason": "missing_x_bearer_token",
            "detail": "X_BEARER_TOKEN belum diisi.",
        }

    url = f"https://api.x.com/2/tweets/{tweet_id}"
    params = {
        "expansions": "attachments.media_keys",
        "media.fields": "type,url,preview_image_url,variants",
    }
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return {
            "ok": False,
            "media": [],
            "reason": "x_api_error",
            "status_code": response.status_code,
            "detail": summarize_x_error(response),
        }

    data = response.json()
    media_items = data.get("includes", {}).get("media", [])

    if not media_items:
        return {
            "ok": False,
            "media": [],
            "reason": "no_media",
            "status_code": response.status_code,
            "detail": "X API tidak mengembalikan media untuk tweet ini.",
        }

    media_urls = []
    for media in media_items:
        if media.get("type") == "photo" and media.get("url"):
            media_urls.append({"url": media["url"], "extension": ".jpg"})
            continue

        if media.get("type") in ["video", "animated_gif"]:
            video_url = pick_best_video(media)
            if video_url:
                media_urls.append({"url": video_url, "extension": ".mp4"})

    if media_urls:
        return {
            "ok": True,
            "media": media_urls,
            "reason": "ok",
            "status_code": response.status_code,
            "detail": "",
        }

    return {
        "ok": False,
        "media": [],
        "reason": "no_video_media",
        "status_code": response.status_code,
        "detail": "Media ada, tapi tipenya belum didukung.",
    }


async def get_media_urls_from_fxtwitter(tweet_id: str) -> dict:
    url = f"https://api.fxtwitter.com/status/{tweet_id}"
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)

    try:
        data = response.json()
    except Exception:
        return {
            "ok": False,
            "media": [],
            "reason": "fxtwitter_invalid_json",
            "detail": response.text[:220],
        }

    if response.status_code != 200 or data.get("code") != 200:
        return {
            "ok": False,
            "media": [],
            "reason": "fxtwitter_error",
            "status_code": response.status_code,
            "detail": data.get("message") or str(data)[:220],
        }

    media = data.get("tweet", {}).get("media", {})
    media_items = media.get("all") or media.get("photos") or media.get("videos") or []
    media_urls = []

    for item in media_items:
        media_url = item.get("url")
        media_type = item.get("type")
        media_format = item.get("format", "")

        if not media_url:
            continue

        if media_type == "photo" or media_format.startswith("image/"):
            media_urls.append({"url": media_url, "extension": ".jpg"})
        elif media_type in {"video", "gif"} or media_format.startswith("video/"):
            media_urls.append({"url": media_url, "extension": ".mp4"})

    if media_urls:
        return {
            "ok": True,
            "media": media_urls,
            "reason": "ok",
            "detail": "",
            "source": "fxtwitter-fallback",
        }

    return {
        "ok": False,
        "media": [],
        "reason": "fxtwitter_no_supported_media",
        "detail": "FxTwitter tidak mengembalikan media yang didukung.",
    }


def collect_media_urls_from_x_payload(data) -> list[dict]:
    media_urls = []
    seen = set()

    def add_media(url: Optional[str], extension: str) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        media_urls.append({"url": url, "extension": extension})

    def walk(value) -> None:
        if isinstance(value, dict):
            media_type = value.get("type")
            media_url = value.get("media_url_https") or value.get("media_url")

            if media_type == "photo" and media_url:
                add_media(f"{media_url}?name=orig", ".jpg")

            video_info = value.get("video_info")
            if isinstance(video_info, dict):
                variants = [
                    variant
                    for variant in video_info.get("variants", [])
                    if variant.get("content_type") == "video/mp4" and variant.get("url")
                ]
                if variants:
                    best_variant = max(variants, key=lambda item: item.get("bitrate", 0))
                    add_media(best_variant.get("url"), ".mp4")

            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return media_urls


async def get_media_urls_from_x_web(tweet_id: str, original_url: str) -> dict:
    cookie_file = get_cookie_file(original_url)
    cookies = load_netscape_cookie_dict(cookie_file, original_url)
    ct0 = cookies.get("ct0")

    if not cookies or not ct0:
        return {
            "ok": False,
            "media": [],
            "reason": "missing_x_web_cookies",
            "detail": "Cookie X belum lengkap untuk akses web internal.",
        }

    variables = {
        "tweetId": tweet_id,
        "withCommunity": False,
        "includePromotedContent": False,
        "withVoice": False,
    }
    features = {
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "premium_content_api_read_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
        "responsive_web_grok_analyze_post_followups_enabled": True,
        "responsive_web_jetfuel_frame": False,
        "responsive_web_grok_share_attachment_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "responsive_web_grok_show_grok_translated_post": False,
        "responsive_web_grok_analysis_button_from_backend": True,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_grok_image_annotation_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }
    field_toggles = {
        "withArticleRichContentState": True,
        "withArticlePlainText": False,
        "withGrokAnalyze": False,
        "withDisallowedReplyControls": False,
    }
    endpoint = f"https://x.com/i/api/graphql/{X_TWEET_RESULT_QUERY_ID}/TweetResultByRestId"
    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(features, separators=(",", ":")),
        "fieldToggles": json.dumps(field_toggles, separators=(",", ":")),
    }
    headers = {
        "authorization": f"Bearer {X_WEB_BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "id",
        "referer": original_url,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(endpoint, params=params, cookies=cookies, headers=headers)

    try:
        data = response.json()
    except Exception:
        return {
            "ok": False,
            "media": [],
            "reason": "x_web_invalid_json",
            "status_code": response.status_code,
            "detail": response.text[:220],
        }

    if response.status_code != 200 or data.get("errors"):
        return {
            "ok": False,
            "media": [],
            "reason": "x_web_error",
            "status_code": response.status_code,
            "detail": str(data.get("errors") or data)[:220],
        }

    media_urls = collect_media_urls_from_x_payload(data)
    if media_urls:
        return {
            "ok": True,
            "media": media_urls,
            "reason": "ok",
            "detail": "",
            "source": "x-web-fallback",
        }

    return {
        "ok": False,
        "media": [],
        "reason": "x_web_no_supported_media",
        "detail": "X web tidak mengembalikan media yang didukung.",
    }


async def download_video(video_url: str, save_path: Path) -> bool:
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        async with client.stream("GET", video_url) as response:
            if response.status_code != 200:
                return False

            with open(save_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

    return True


def run_video_tagger(video_path: Path) -> dict:
    """Jalankan video tagger, balikin JSON hasil."""
    if not TAGGER_PYTHON.exists() or not TAGGER_SCRIPT.exists():
        return {"status": "no_tagger"}

    try:
        import subprocess
        result = subprocess.run(
            [
                str(TAGGER_PYTHON),
                str(TAGGER_SCRIPT),
                str(video_path),
                "--every-seconds",
                "8",
                "--max-frames",
                "4",
                "--top-k",
                "12",
                "--no-clip",
            ],
            capture_output=True, text=True, timeout=TAGGER_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            logger.warning("tagger stderr: %s", result.stderr[:300])
            return {"status": "error", "stderr": result.stderr[:300]}

        return json.loads(result.stdout)
    except Exception as exc:
        logger.warning("tagger exception: %s", exc)
        return {"status": "error", "detail": str(exc)[:200]}


def build_adult_caption(
    site_name: str,
    topic_name: str,
    original_url: str,
    tags: list[str],
    category: str,
    user_tags: Optional[list[str]] = None,
) -> str:
    """Bikin caption spicy + hashtag dari hasil tagger."""
    is_adult = category == "adult" or bool(tags)
    clean_user_tags = [normalize_tag(tag) for tag in (user_tags or []) if normalize_tag(tag)]
    final_tags = (
        enrich_adult_tags(tags, topic_name, clean_user_tags)
        if is_adult
        else clean_user_tags + ["#adult", "#nsfw", "#18plus"]
    )
    hashtags = " ".join(final_tags)
    manual_tag_names = ", ".join(tag.removeprefix("#") for tag in clean_user_tags)

    # Pilih vibe caption
    vibe_options = [
        "susu gede banget, bodinya semok parah",
        "bokong semok sama body montoknya dapet banget",
        "panas bet ini, vibes nakalnya kerasa dari awal",
        "montoknya gak main-main, cocok buat tontonan malam",
        "susu gede, paha mulus, paketnya komplit banget",
        "body semok begini wajib masuk arsip bang Zekk",
        "vibe adult-nya kuat, bikin makin greget",
        "ini mah spicy banget, auto disave dulu",
        "bokongnya semok, bodinya bikin panas",
        "mantap bet, aura nakalnya keluar semua",
        "body kayak gini harusnya ilegal, semok parah",
        "warning: jangan ditonton sambil puasa mata",
        "save dulu, mikir belakangan, ini bahaya",
        "nih yang bikin kuota gak pernah cukup, nakal banget",
        "auto begadang gara-gara satu clip doang",
        "niat tidur cepet, batal gara-gara ini",
        "sumpah ini cobaan iman level akhir",
        "kategori 'mending gak usah liat' tapi tetep diliat",
        "semok-nya gak wajar, kayak sengaja dibikin nyiksa",
        "clip beginian harusnya pake disclaimer",
    ]

    import random
    vibe = random.choice(vibe_options)

    lines = [
        f"{vibe} 🔥",
        "",
        "📥 Auto-download dari Telegram",
        f"🌐 {site_name}",
        f"📂 Topic: {topic_name}",
        *([f"🏷 Tag: {manual_tag_names}"] if manual_tag_names else []),
        f"🔗 {original_url}",
        "",
        f"{hashtags}",
    ]
    return "\n".join(lines)


def cookie_domain_matches(cookie_domain: str, request_host: str) -> bool:
    cookie_domain = cookie_domain.lower().lstrip(".")
    request_host = request_host.lower()
    return request_host == cookie_domain or request_host.endswith(f".{cookie_domain}")


def load_netscape_cookie_dict(
    cookie_file: Optional[str],
    request_url: str,
    extra_match_urls: Optional[list[str]] = None,
) -> dict[str, str]:
    if not cookie_file:
        return {}

    match_hosts = [urlparse(request_url).netloc.lower()]
    for match_url in extra_match_urls or []:
        match_host = urlparse(match_url).netloc.lower()
        if match_host and match_host not in match_hosts:
            match_hosts.append(match_host)

    cookies = {}

    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith("#HttpOnly_"):
                    line = line.removeprefix("#HttpOnly_")
                elif line.startswith("#"):
                    continue

                fields = line.split("\t")
                if len(fields) < 7:
                    fields = line.split(None, 6)
                if len(fields) < 7:
                    continue

                domain, _, _, _, _, name, value = fields[:7]
                if any(cookie_domain_matches(domain, host) for host in match_hosts):
                    cookies[name] = value
    except Exception as exc:
        logger.warning("failed to load cookie file=%s error=%s", cookie_file, str(exc)[:120])

    return cookies


def extension_from_media_url(media_url: str, fallback_extension: str) -> str:
    extension = Path(urlparse(media_url).path).suffix.lower()
    if extension in {".mp4", ".m4v", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return extension

    fallback_extension = fallback_extension if fallback_extension.startswith(".") else f".{fallback_extension}"
    return fallback_extension.lower()


def resolve_cookie_path(cookie_value: Optional[str]) -> Optional[str]:
    """Resolve a cookie file path from env value, with fallback to BASE_DIR."""
    if not cookie_value:
        return None

    cookie_path = Path(cookie_value).expanduser()
    if not cookie_path.is_absolute():
        cookie_path = BASE_DIR / cookie_path

    return str(cookie_path) if cookie_path.exists() else None


def get_cookie_file(url: str) -> Optional[str]:
    """Get the best cookie file for a URL, checking platform-specific then default."""
    # First try shared module's env-based lookup
    platform = platform_key_from_url(url)
    env_key_map = {
        "x": "X_COOKIES_FILE",
        "instagram": "INSTAGRAM_COOKIES_FILE",
        "tiktok": "TIKTOK_COOKIES_FILE",
        "youtube": "YOUTUBE_COOKIES_FILE",
        "facebook": "FACEBOOK_COOKIES_FILE",
    }
    env_key = env_key_map.get(platform)
    if env_key:
        platform_cookie = resolve_cookie_path(os.getenv(env_key))
        if platform_cookie:
            return platform_cookie

    # Then try default
    default_cookie = resolve_cookie_path(os.getenv("COOKIES_FILE"))
    if default_cookie:
        return default_cookie

    # Last resort
    default_file = BASE_DIR / "cookies.txt"
    return str(default_file) if default_file.exists() else None


async def download_direct_media_urls(
    media_items: list[dict],
    original_url: str,
    group_name: str,
    topic_name: str,
) -> dict:
    cookie_file = get_cookie_file(original_url)
    cookie_used = False
    downloaded_files = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Referer": original_url,
    }

    async with httpx.AsyncClient(timeout=180, follow_redirects=True, headers=headers) as client:
        for media in media_items:
            media_url = media.get("url")
            if not media_url:
                continue

            extension = extension_from_media_url(media_url, media.get("extension", ".jpg"))
            save_path = build_save_path(group_name, topic_name, extension)
            request_cookies = load_netscape_cookie_dict(
                cookie_file,
                media_url,
                extra_match_urls=[original_url],
            )
            cookie_used = cookie_used or bool(request_cookies)
            request_headers = {}
            if request_cookies:
                request_headers["Cookie"] = "; ".join(
                    f"{name}={value}" for name, value in request_cookies.items()
                )

            try:
                async with client.stream("GET", media_url, headers=request_headers or None) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "direct media download failed status=%s url=%s",
                            response.status_code,
                            media_url,
                        )
                        continue

                    with open(save_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)

                downloaded_files.append(save_path)
            except Exception as exc:
                logger.warning("direct media download exception url=%s error=%s", media_url, str(exc)[:200])

    return {
        "ok": bool(downloaded_files),
        "files": downloaded_files,
        "error": "" if downloaded_files else "Fallback media langsung tidak menghasilkan file output.",
        "cookie_used": cookie_used,
        "source": "direct-media",
    }


def download_with_ytdlp_sync(original_url: str, group_name: str, topic_name: str) -> dict:
    folder = get_save_folder(group_name, topic_name)
    start_index = next_file_index(folder, topic_name)
    before = {path.resolve() for path in folder.iterdir() if is_downloaded_media_file(path)}
    output_template = str(folder / f"{safe_name(topic_name)}-%(autonumber)d.%(ext)s")

    options = {
        "outtmpl": output_template,
        "autonumber_start": start_index,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "restrictfilenames": False,
        "writethumbnail": False,
        "writeinfojson": False,
    }
    cookie_file = get_cookie_file(original_url)

    if cookie_file:
        options["cookiefile"] = cookie_file

    attempts = [
        {
            **options,
            "format": "bestvideo*+bestaudio/best",
            "merge_output_format": "mp4",
        },
        options,
    ]
    last_error = ""

    for attempt_index, attempt_options in enumerate(attempts, start=1):
        try:
            logger.info(
                "download start attempt=%s site=%s topic=%s url=%s",
                attempt_index,
                site_name_from_url(original_url),
                topic_name,
                original_url,
            )
            with yt_dlp.YoutubeDL(attempt_options) as ydl:
                ydl.download([original_url])
        except Exception as exc:
            last_error = str(exc)[:400]
            logger.exception("download failed attempt=%s url=%s", attempt_index, original_url)
            continue

        after_attempt = [path for path in folder.iterdir() if is_downloaded_media_file(path)]
        if any(path.resolve() not in before for path in after_attempt):
            break

    after = [path for path in folder.iterdir() if is_downloaded_media_file(path)]
    files = sorted(
        [path for path in after if path.resolve() not in before],
        key=lambda path: path.stat().st_mtime,
    )

    return {
        "ok": bool(files),
        "files": files,
        "error": "" if files else (last_error or "yt-dlp tidak menghasilkan file output."),
        "cookie_used": bool(cookie_file),
        "source": "yt-dlp",
    }


async def download_with_ytdlp(original_url: str, group_name: str, topic_name: str) -> dict:
    return await asyncio.to_thread(
        download_with_ytdlp_sync,
        original_url,
        group_name,
        topic_name,
    )


async def download_x_media_fallback(
    tweet_id: str,
    original_url: str,
    group_name: str,
    topic_name: str,
) -> dict:
    x_media = await get_media_urls_from_fxtwitter(tweet_id)
    if not x_media.get("ok"):
        logger.info(
            "FxTwitter fallback failed reason=%s detail=%s",
            x_media.get("reason"),
            str(x_media.get("detail", ""))[:160],
        )
        x_media = await get_media_urls_from_x_web(tweet_id, original_url)

    if not x_media.get("ok"):
        logger.info(
            "X web fallback failed reason=%s detail=%s",
            x_media.get("reason"),
            str(x_media.get("detail", ""))[:160],
        )
        x_media = await get_media_urls_from_x(tweet_id)

    if not x_media.get("ok"):
        return {
            "ok": False,
            "files": [],
            "error": x_media.get("detail") or x_media.get("reason") or "X media fallback gagal.",
            "cookie_used": False,
            "source": "x-api-fallback",
        }

    result = await download_direct_media_urls(
        x_media.get("media", []),
        original_url,
        group_name,
        topic_name,
    )
    result["source"] = x_media.get("source", "x-media-fallback")
    return result


async def send_telegram_message(
    chat_id: int,
    message_thread_id: Optional[int],
    text: str,
) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    if message_thread_id:
        payload["message_thread_id"] = message_thread_id

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)

    if response.status_code != 200:
        logger.error("telegram message send failed status=%s body=%s", response.status_code, response.text[:500])
        return

    result = response.json().get("result", {})
    message_id = result.get("message_id")
    if message_id:
        record_bot_cleanup_message(chat_id, message_thread_id, message_id)

    if is_cleanup_enabled(chat_id, message_thread_id):
        if message_id:
            asyncio.create_task(delete_telegram_message_later(chat_id, message_id, 8))


async def delete_telegram_message_later(
    chat_id: int,
    message_id: int,
    delay_seconds: float = 0,
) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.warning("telegram delete failed status=%s body=%s", response.status_code, response.text[:300])
        else:
            mark_cleanup_message_deleted(chat_id, message_id)
    except Exception as exc:
        logger.warning("telegram delete exception chat_id=%s message_id=%s error=%s", chat_id, message_id, str(exc)[:160])


RETRYABLE_TELEGRAM_STATUSES = {429, 500, 502, 503, 504}


async def send_telegram_file(
    chat_id: int,
    message_thread_id: Optional[int],
    file_path_or_id: str,
    caption: str,
    max_retries: int = 3,
):
    """Send media to Telegram with retry on transient errors (429, 5xx)."""
    media_kind = telegram_media_kind(file_path_or_id)

    if media_kind == "video":
        method = "sendVideo"
        field_name = "video"
        result_key = "video"
    elif media_kind == "photo":
        method = "sendPhoto"
        field_name = "photo"
        result_key = "photo"
    else:
        method = "sendDocument"
        field_name = "document"
        result_key = "document"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = {
        "chat_id": str(chat_id),
        "caption": caption,
    }

    if message_thread_id:
        data["message_thread_id"] = str(message_thread_id)

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=240) as client:
                if os.path.exists(file_path_or_id):
                    with open(file_path_or_id, "rb") as media_file:
                        files = {field_name: media_file}
                        response = await client.post(url, data=data, files=files)
                else:
                    data[field_name] = file_path_or_id
                    response = await client.post(url, data=data)

            if response.status_code == 200:
                result = response.json()
                media = result.get("result", {}).get(result_key, {})

                if result_key == "photo" and isinstance(media, list) and media:
                    file_id = media[-1].get("file_id")
                elif isinstance(media, dict):
                    file_id = media.get("file_id")
                else:
                    file_id = None

                return True, file_id

            last_error = f"status={response.status_code} body={response.text[:200]}"

            if response.status_code not in RETRYABLE_TELEGRAM_STATUSES:
                break  # non-retryable error (400, 403, etc)

            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(
                    "telegram send retry attempt=%s/%s wait=%ss status=%s",
                    attempt, max_retries, wait, response.status_code,
                )
                await asyncio.sleep(wait)
        except Exception as exc:
            last_error = str(exc)[:200]
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    "telegram send retry attempt=%s/%s wait=%ss error=%s",
                    attempt, max_retries, wait, str(exc)[:120],
                )
                await asyncio.sleep(wait)

    logger.error("telegram send failed after %s retries: %s", max_retries, last_error)
    return False, None


def extract_file_id_from_message(message: dict) -> Optional[str]:
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        return photos[-1].get("file_id")

    for key in ("video", "document"):
        media = message.get(key)
        if isinstance(media, dict):
            return media.get("file_id")

    return None


async def send_telegram_media_group(
    chat_id: int,
    message_thread_id: Optional[int],
    file_path_or_ids: list[str],
    caption: str,
) -> tuple[bool, list[str]]:
    """Kirim photo/video sebagai satu album Telegram. Caption hanya di item pertama."""
    supported_items = [
        item for item in file_path_or_ids if telegram_media_kind(item) in {"photo", "video"}
    ]
    if not supported_items:
        return False, []

    file_ids: list[str] = []
    ok_all = True

    # Telegram sendMediaGroup max 10 item per request.
    for chunk_index in range(0, len(supported_items), 10):
        chunk = supported_items[chunk_index:chunk_index + 10]
        media_payload = []
        files = {}
        opened_files = []

        try:
            for index, item in enumerate(chunk):
                media_kind = telegram_media_kind(item)
                media_item = {
                    "type": media_kind,
                }

                if os.path.exists(item):
                    attach_name = f"media_{chunk_index}_{index}"
                    opened_file = open(item, "rb")
                    opened_files.append(opened_file)
                    files[attach_name] = opened_file
                    media_item["media"] = f"attach://{attach_name}"
                else:
                    media_item["media"] = item

                if chunk_index == 0 and index == 0:
                    media_item["caption"] = caption

                media_payload.append(media_item)

            data = {
                "chat_id": str(chat_id),
                "media": json.dumps(media_payload, ensure_ascii=False),
            }
            if message_thread_id:
                data["message_thread_id"] = str(message_thread_id)

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(url, data=data, files=files or None)

            if response.status_code != 200:
                logger.error(
                    "telegram media group failed status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                ok_all = False
                continue

            result = response.json()
            for message in result.get("result", []):
                file_id = extract_file_id_from_message(message)
                if file_id:
                    file_ids.append(file_id)
        finally:
            for opened_file in opened_files:
                opened_file.close()

    return ok_all, file_ids


async def send_telegram_files(
    chat_id: int,
    message_thread_id: Optional[int],
    file_path_or_ids: list[str],
    caption: str,
) -> tuple[bool, list[str]]:
    if not file_path_or_ids:
        return False, []

    if len(file_path_or_ids) == 1:
        ok, file_id = await send_telegram_file(
            chat_id,
            message_thread_id,
            file_path_or_ids[0],
            caption,
        )
        return ok, [file_id] if file_id else []

    if all(telegram_media_kind(item) in {"photo", "video"} for item in file_path_or_ids):
        return await send_telegram_media_group(
            chat_id,
            message_thread_id,
            file_path_or_ids,
            caption,
        )

    ok_all = True
    file_ids = []
    for index, item in enumerate(file_path_or_ids, start=1):
        item_caption = caption if index == 1 else ""
        ok, file_id = await send_telegram_file(
            chat_id,
            message_thread_id,
            item,
            item_caption,
        )
        ok_all = ok_all and ok
        if file_id:
            file_ids.append(file_id)

    return ok_all, file_ids


@app.on_event("startup")
async def startup_event() -> None:
    init_all_db()
    asyncio.create_task(queue_worker())
    logger.info("worker startup complete")


@app.get("/health")
async def health() -> dict:
    loaded = {}
    for key in ("default", "x", "instagram", "tiktok", "youtube", "facebook"):
        path = resolve_cookie_path(COOKIE_FILES.get(key))
        loaded[key] = bool(path)
    return {
        "ok": True,
        "queue_size": WORK_QUEUE.qsize(),
        "cookies_loaded": loaded,
        "tagger": TAGGER_SCRIPT.exists() and TAGGER_PYTHON.exists(),
    }


@app.post("/twitter-video")
async def twitter_video(req: TwitterVideoRequest):
    job_id = uuid4().hex[:12]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    await WORK_QUEUE.put((job_id, req, future))
    logger.info("queued job=%s queue_size=%s url=%s", job_id, WORK_QUEUE.qsize(), req.original_url)
    return await future


async def queue_worker() -> None:
    while True:
        job_id, req, future = await WORK_QUEUE.get()

        try:
            logger.info("processing job=%s url=%s", job_id, req.original_url)
            result = await process_media_request(req)
            if not future.done():
                future.set_result(result)
            logger.info("done job=%s ok=%s", job_id, result.get("ok"))
        except Exception as exc:
            logger.exception("job failed job=%s", job_id)
            if not future.done():
                future.set_result({"ok": False, "reason": "worker_exception", "detail": str(exc)[:400]})
        finally:
            WORK_QUEUE.task_done()


async def process_media_request(req: TwitterVideoRequest):
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "reason": "missing_env"}

    group_name = req.group_name or str(req.chat_id)
    topic_name = get_topic_name(req.chat_id, req.message_thread_id)

    cached = get_cache(req.tweet_id)

    if cached and cached[0]:
        site_name = site_name_from_url(req.original_url)
        cached_items = decode_cache_items(cached[1]) or decode_cache_items(cached[0])

        # Coba tag ulang dari file lokal kalau ada
        tags = []
        tag_category = "adult"
        for item in cached_items:
            if is_local_video_file(item):
                tagger_result = run_video_tagger(Path(item))
                if tagger_result.get("classification", {}).get("status") == "ok":
                    tags = tagger_result["classification"].get("tags", [])
                    if tags:
                        tag_category = tagger_result["classification"].get("category", "adult")
                break

        caption = build_adult_caption(
            site_name,
            topic_name,
            req.original_url,
            tags,
            tag_category,
            req.user_tags,
        )

        ok, _ = await send_telegram_files(
            req.chat_id,
            req.message_thread_id,
            cached_items,
            caption,
        )
        return {"ok": ok, "cached": True}

    ytdlp_result = await download_with_ytdlp(req.original_url, group_name, topic_name)
    if not ytdlp_result["ok"] and platform_key_from_url(req.original_url) == "x":
        logger.info("yt-dlp failed for X media, trying image/media fallback url=%s", req.original_url)
        fallback_result = await download_x_media_fallback(
            req.tweet_id,
            req.original_url,
            group_name,
            topic_name,
        )
        if fallback_result["ok"]:
            ytdlp_result = fallback_result

    if ytdlp_result["ok"]:
        # Jalankan tagger untuk video pertama
        tags = []
        tag_category = "adult"
        first_video = next(
            (file_path for file_path in ytdlp_result["files"] if is_local_video_file(str(file_path))),
            None,
        )
        if first_video:
            tagger_result = run_video_tagger(first_video)
            if tagger_result.get("classification", {}).get("status") == "ok":
                tags = tagger_result["classification"].get("tags", [])
                if tags:
                    tag_category = tagger_result["classification"].get("category", "adult")

        site_name = site_name_from_url(req.original_url)
        caption = build_adult_caption(
            site_name,
            topic_name,
            req.original_url,
            tags,
            tag_category,
            req.user_tags,
        )

        saved_paths = [str(file_path) for file_path in ytdlp_result["files"]]
        ok, file_ids = await send_telegram_files(
            req.chat_id,
            req.message_thread_id,
            saved_paths,
            caption,
        )

        if file_ids:
            save_cache(
                req.tweet_id,
                encode_cache_items(file_ids),
                encode_cache_items(saved_paths),
                req.original_url,
            )

        return {
            "ok": ok,
            "saved_to": saved_paths,
            "topic": topic_name,
            "source": ytdlp_result.get("source", "yt-dlp"),
            "cookie_used": ytdlp_result.get("cookie_used", False),
        }

    await send_telegram_message(
        req.chat_id,
        req.message_thread_id,
        "Media belum bisa didownload langsung dari link ini.\n"
        f"Detail: {ytdlp_result['error']}",
    )
    return {
        "ok": False,
        "reason": "ytdlp_failed",
        "detail": ytdlp_result["error"],
    }


# ============================================================
# Dashboard / Web Control Panel
# ============================================================

def _check_dashboard_auth(token: Optional[str]) -> None:
    if not DASHBOARD_TOKEN:
        return  # token gak diset di .env -> akses lokal bebas
    if not token or not secrets.compare_digest(token, DASHBOARD_TOKEN):
        raise HTTPException(status_code=401, detail="Token salah atau kosong.")


def _bot_running() -> bool:
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_text(encoding="utf-8")
            except Exception:
                continue
            if "scripts/bot.py" in cmdline:
                return True
    except Exception:
        pass
    return False


def _supervisor_running() -> bool:
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_text(encoding="utf-8")
            except Exception:
                continue
            if "supervisor.sh" in cmdline:
                return True
    except Exception:
        pass
    return False


def _cookie_status() -> list[dict]:
    rows = []
    for platform, filename in COOKIE_PLATFORM_FILES.items():
        path = COOKIES_DIR / filename
        exists = path.exists() and path.stat().st_size > 0
        rows.append({
            "platform": platform,
            "filename": filename,
            "loaded": exists,
            "size": path.stat().st_size if exists else 0,
            "updated": int(path.stat().st_mtime) if exists else 0,
        })
    return rows


def _load_cleanup_settings() -> dict:
    if not CLEANUP_FILE.exists():
        return {}
    try:
        return json.loads(CLEANUP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.get("/api/status")
async def api_status(x_dashboard_token: Optional[str] = Header(default=None)):
    _check_dashboard_auth(x_dashboard_token)
    return {
        "worker": True,
        "bot": _bot_running(),
        "supervisor": _supervisor_running(),
        "queue_size": WORK_QUEUE.qsize(),
        "tagger": TAGGER_SCRIPT.exists() and TAGGER_PYTHON.exists(),
        "cookies": _cookie_status(),
        "cleanup_active": len(_load_cleanup_settings()),
        "telegram_token_set": bool(TELEGRAM_BOT_TOKEN),
    }


@app.post("/api/cookies/{platform}")
async def api_upload_cookie(
    platform: str,
    file: UploadFile = File(...),
    x_dashboard_token: Optional[str] = Header(default=None),
):
    _check_dashboard_auth(x_dashboard_token)
    if platform not in COOKIE_PLATFORM_FILES:
        raise HTTPException(status_code=400, detail="Platform gak dikenal.")

    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="File kegedean (>2MB).")
    text = raw.decode("utf-8", errors="replace")
    ok, _ = validate_cookie_text(text)
    if not ok:
        raise HTTPException(status_code=400, detail="Format cookie gak valid (pakai Netscape cookies.txt).")

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    dest = COOKIES_DIR / COOKIE_PLATFORM_FILES[platform]
    dest.write_text(text, encoding="utf-8")
    logger.info("dashboard cookie upload platform=%s bytes=%s", platform, len(text))
    return {"ok": True, "platform": platform, "size": len(text)}


@app.delete("/api/cookies/{platform}")
async def api_delete_cookie(
    platform: str,
    x_dashboard_token: Optional[str] = Header(default=None),
):
    _check_dashboard_auth(x_dashboard_token)
    if platform not in COOKIE_PLATFORM_FILES:
        raise HTTPException(status_code=400, detail="Platform gak dikenal.")
    dest = COOKIES_DIR / COOKIE_PLATFORM_FILES[platform]
    if dest.exists():
        dest.unlink()
        logger.info("dashboard cookie deleted platform=%s", platform)
    return {"ok": True, "platform": platform}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    html = read_dashboard_asset(
        DASHBOARD_HTML_FILE,
        "<h1>Dashboard asset tidak ditemukan</h1><p>scripts/dashboard.html hilang.</p>",
    )
    return HTMLResponse(html)


@app.get("/dashboard.js")
async def dashboard_js():
    js = read_dashboard_asset(DASHBOARD_JS_FILE, "// dashboard.js tidak ditemukan")
    return Response(content=js, media_type="application/javascript")


if __name__ == "__main__":
    init_all_db()
    logger.info("dashboard at http://%s:%s/dashboard", WORKER_HOST, WORKER_PORT)
    uvicorn.run(app, host=WORKER_HOST, port=WORKER_PORT)
