"""
Shared utilities for bot.py and worker.py.
Database connections, cleanup settings, platform detection, cookie validation.
"""

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
COOKIES_DIR = BASE_DIR / "cookies"
LOG_DIR = BASE_DIR / "logs"
CLEANUP_FILE = Path(__file__).resolve().parent / "cleanup_settings.json"
CACHE_DB = BASE_DIR / "telegram_x_video_cache.sqlite3"
TOPICS_FILE = Path(__file__).resolve().parent / "topics.json"

SUPPORTED_DOMAINS = (
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "fb.watch",
    "instagram.com",
)

COOKIE_PLATFORM_FILES: dict[str, str] = {
    "x": "x.txt",
    "instagram": "instagram.txt",
    "tiktok": "tiktok.txt",
    "youtube": "youtube.txt",
    "facebook": "facebook.txt",
}

COOKIE_PLATFORMS: dict[str, str] = {
    "x": "x.txt",
    "twitter": "x.txt",
    "instagram": "instagram.txt",
    "ig": "instagram.txt",
    "tiktok": "tiktok.txt",
    "youtube": "youtube.txt",
    "yt": "youtube.txt",
    "facebook": "facebook.txt",
    "fb": "facebook.txt",
}

URL_REGEX = r"https?://[^\s<>]+"

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("telegram-x-video-shared")


# ---------------------------------------------------------------------------
# Database helpers – WAL mode, shared connection utilities
# ---------------------------------------------------------------------------

def get_db_path() -> Path:
    return CACHE_DB


def db_connect() -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and optimizations enabled."""
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def db_execute(sql: str, params: tuple = ()) -> None:
    """Execute a write statement and commit immediately."""
    with db_connect() as conn:
        conn.execute(sql, params)


def db_fetchone(sql: str, params: tuple = ()):
    """Fetch a single row."""
    with db_connect() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def db_fetchall(sql: str, params: tuple = ()):
    """Fetch all rows."""
    with db_connect() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Schema initialization – called once by both bot and worker
# ---------------------------------------------------------------------------

def init_message_log_table() -> None:
    """Create/upgrade message_cleanup_log table."""
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_cleanup_log (
                chat_id INTEGER NOT NULL,
                message_thread_id INTEGER,
                message_id INTEGER NOT NULL,
                sender TEXT NOT NULL DEFAULT 'user',
                keep INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(message_cleanup_log)")
        }
        if "sender" not in columns:
            conn.execute(
                "ALTER TABLE message_cleanup_log ADD COLUMN sender TEXT NOT NULL DEFAULT 'user'"
            )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_message_cleanup_log_scope
            ON message_cleanup_log (chat_id, message_thread_id, sender, deleted, message_id)
            """
        )


def init_cache_table() -> None:
    """Create video_cache table if not exists."""
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS video_cache (
                tweet_id TEXT PRIMARY KEY,
                telegram_file_id TEXT,
                local_path TEXT,
                original_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def init_all_db() -> None:
    """Initialize all database tables (idempotent)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    init_message_log_table()
    init_cache_table()


# ---------------------------------------------------------------------------
# Cleanup settings helpers
# ---------------------------------------------------------------------------

def cleanup_key(chat_id: int, message_thread_id: Optional[int]) -> str:
    return f"{chat_id}:{message_thread_id or 0}"


def load_cleanup_settings() -> dict:
    if not CLEANUP_FILE.exists():
        return {}

    try:
        with open(CLEANUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cleanup_settings(settings: dict) -> None:
    with open(CLEANUP_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def is_cleanup_enabled(chat_id: int, message_thread_id: Optional[int]) -> bool:
    settings = load_cleanup_settings()
    return bool(
        settings.get(cleanup_key(chat_id, message_thread_id))
        or settings.get(cleanup_key(chat_id, None))
    )


def set_cleanup_enabled(
    chat_id: int,
    message_thread_id: Optional[int],
    enabled: bool,
) -> None:
    settings = load_cleanup_settings()
    key = cleanup_key(chat_id, None)

    if enabled:
        settings[key] = True
    else:
        settings.pop(key, None)

    save_cleanup_settings(settings)


# ---------------------------------------------------------------------------
# Cleanup log operations
# ---------------------------------------------------------------------------

def record_cleanup_message(
    chat_id: int,
    message_thread_id: Optional[int],
    message_id: int,
    sender: str,
) -> None:
    db_execute(
        """
        INSERT OR IGNORE INTO message_cleanup_log
        (chat_id, message_thread_id, message_id, sender, keep, deleted)
        VALUES (?, ?, ?, ?, 0, 0)
        """,
        (chat_id, message_thread_id, message_id, sender),
    )


def record_bot_cleanup_message(
    chat_id: int,
    message_thread_id: Optional[int],
    message_id: int,
) -> None:
    record_cleanup_message(chat_id, message_thread_id, message_id, "bot")


def mark_cleanup_message_deleted(chat_id: int, message_id: int) -> None:
    db_execute(
        """
        UPDATE message_cleanup_log
        SET deleted = 1
        WHERE chat_id = ? AND message_id = ?
        """,
        (chat_id, message_id),
    )


def get_cleanup_candidates(
    chat_id: int,
    message_thread_id: Optional[int],
    limit: int,
    sender: str,
    all_topics: bool = False,
) -> list[int]:
    topic_filter = "" if all_topics else "AND COALESCE(message_thread_id, 0) = ?"
    params: list = [chat_id, sender]
    if not all_topics:
        params.append(message_thread_id or 0)
    params.append(limit)

    rows = db_fetchall(
        f"""
        SELECT message_id
        FROM message_cleanup_log
        WHERE chat_id = ?
          AND sender = ?
          {topic_filter}
          AND keep = 0
          AND deleted = 0
        ORDER BY message_id DESC
        LIMIT ?
        """,
        tuple(params),
    )

    return [int(row[0]) for row in rows]


# ---------------------------------------------------------------------------
# Cache operations
# ---------------------------------------------------------------------------

def get_cache(tweet_id: str):
    return db_fetchone(
        "SELECT telegram_file_id, local_path FROM video_cache WHERE tweet_id = ?",
        (tweet_id,),
    )


def save_cache(
    tweet_id: str,
    telegram_file_id: Optional[str],
    local_path: str,
    original_url: str,
) -> None:
    db_execute(
        """
        INSERT OR REPLACE INTO video_cache
        (tweet_id, telegram_file_id, local_path, original_url)
        VALUES (?, ?, ?, ?)
        """,
        (tweet_id, telegram_file_id, local_path, original_url),
    )


# ---------------------------------------------------------------------------
# URL / platform helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    return url.rstrip(").,]")


def is_supported_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    return any(domain == item or domain.endswith(f".{item}") for item in SUPPORTED_DOMAINS)


def media_id_from_url(url: str) -> str:
    import hashlib

    twitter_match = re.search(
        r"https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/(\d+)",
        url,
    )
    if twitter_match:
        return twitter_match.group(1)

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def platform_key_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    if "x.com" in domain or "twitter.com" in domain:
        return "x"
    if "instagram.com" in domain:
        return "instagram"
    if "tiktok.com" in domain:
        return "tiktok"
    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube"
    if "facebook.com" in domain or "fb.watch" in domain:
        return "facebook"
    return None


def site_name_from_url(url: str) -> str:
    key = platform_key_from_url(url)
    name_map = {
        "x": "X / Twitter",
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "youtube": "YouTube",
        "facebook": "Facebook",
    }
    return name_map.get(key or "", "Unknown")


def platform_from_text(text: str) -> Optional[str]:
    """Detect platform name from cookie upload caption."""
    lowered = (text or "").lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))

    for key, filename in COOKIE_PLATFORMS.items():
        if key in words:
            return filename

    for key, filename in COOKIE_PLATFORMS.items():
        if len(key) >= 6 and key in lowered:
            return filename

    return None


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def resolve_cookie_path(cookie_path: Optional[str]) -> Optional[Path]:
    if not cookie_path:
        return None

    raw = Path(cookie_path)
    if raw.is_file() and raw.stat().st_size > 0:
        return raw

    return None


def get_cookie_file(original_url: str) -> Optional[str]:
    platform = platform_key_from_url(original_url)
    if not platform:
        return None

    env_key_map = {
        "x": "X_COOKIES_FILE",
        "instagram": "INSTAGRAM_COOKIES_FILE",
        "tiktok": "TIKTOK_COOKIES_FILE",
        "youtube": "YOUTUBE_COOKIES_FILE",
        "facebook": "FACEBOOK_COOKIES_FILE",
    }

    env_key = env_key_map.get(platform)
    if not env_key:
        return None

    cookie_path = os.getenv(env_key)
    resolved = resolve_cookie_path(cookie_path)
    return str(resolved) if resolved else None


def validate_cookie_text(text: str) -> tuple[bool, str]:
    """Check if text looks like a valid Netscape cookie file or header format."""
    if not text or not text.strip():
        return False, "File cookie kosong."

    lowered = text.lower()
    if "# netscape http cookie file" in lowered or "\t" in text:
        return True, "netscape"
    if "=" in text and ";" in text:
        return True, "header"
    if text.count("\n") >= 1:
        return True, "raw"
    return False, "Format cookie gak dikenali. Pakai export Netscape (cookies.txt)."


# ---------------------------------------------------------------------------
# Topics helpers
# ---------------------------------------------------------------------------

def load_topics() -> dict:
    if not TOPICS_FILE.exists():
        return {}

    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_topic_name(chat_id: int, message_thread_id: Optional[int]) -> str:
    if not message_thread_id:
        return "General"

    topics = load_topics()
    key = f"{chat_id}:{message_thread_id}"
    return topics.get(key, f"Topic-{message_thread_id}")


# ---------------------------------------------------------------------------
# Hashtag extraction
# ---------------------------------------------------------------------------

HASHTAG_REGEX = r"(?<!\w)#([A-Za-z0-9_]{1,50})"


def extract_user_tags(text: str) -> list[str]:
    text_without_urls = re.sub(URL_REGEX, " ", text)
    tags = []

    for match in re.finditer(HASHTAG_REGEX, text_without_urls):
        tag = f"#{match.group(1)}"
        if tag not in tags:
            tags.append(tag)

    return tags[:8]