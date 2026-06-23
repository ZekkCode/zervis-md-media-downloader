import asyncio
import fcntl
import json
import logging
import os
import re
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from dotenv import load_dotenv

from scripts.shared import (
    BASE_DIR,
    COOKIE_PLATFORMS,
    COOKIES_DIR,
    LOG_DIR,
    CLEANUP_FILE,
    URL_REGEX,
    SUPPORTED_DOMAINS,
    cleanup_key,
    db_connect,
    init_message_log_table,
    load_cleanup_settings,
    save_cleanup_settings,
    is_cleanup_enabled,
    set_cleanup_enabled,
    record_cleanup_message,
    record_bot_cleanup_message,
    mark_cleanup_message_deleted,
    get_cleanup_candidates,
    normalize_url,
    is_supported_url,
    media_id_from_url,
    extract_user_tags,
    platform_from_text,
    validate_cookie_text,
)

ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENCLAW_WORKER_URL = os.getenv(
    "OPENCLAW_WORKER_URL",
    "http://127.0.0.1:3000/twitter-video",
)
WORKER_HEALTH_URL = os.getenv(
    "OPENCLAW_WORKER_HEALTH_URL",
    OPENCLAW_WORKER_URL.replace("/twitter-video", "/health"),
)
BOT_LOCK_FILE = LOG_DIR / "bot.lock"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("telegram-media-bot")
BOT_LOCK_HANDLE = None

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN belum diisi di .env")


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pid_is_bot_process(pid: int) -> bool:
    if not pid_is_running(pid):
        return False

    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_text(encoding="utf-8")
    except Exception:
        return False

    return "scripts/bot.py" in cmdline


def acquire_bot_lock() -> None:
    global BOT_LOCK_HANDLE

    BOT_LOCK_HANDLE = open(BOT_LOCK_FILE, "a+", encoding="utf-8")
    try:
        fcntl.flock(BOT_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        BOT_LOCK_HANDLE.seek(0)
        lock_pid_text = BOT_LOCK_HANDLE.read().strip()
        lock_pid = int(lock_pid_text) if lock_pid_text.isdigit() else 0
        if pid_is_bot_process(lock_pid):
            raise RuntimeError("Bot sudah berjalan di proses lain.")

        logger.warning("stale bot lock ignored pid=%s", lock_pid_text or "-")

    BOT_LOCK_HANDLE.seek(0)
    BOT_LOCK_HANDLE.truncate()
    BOT_LOCK_HANDLE.write(str(os.getpid()))
    BOT_LOCK_HANDLE.flush()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Rate limiting: max 5 requests per user per 60 seconds
from collections import defaultdict
import time

_rate_limit_buckets: dict[int, list[float]] = defaultdict(list)
RATE_LIMIT_MAX_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60


def check_rate_limit(user_id: int) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    times = _rate_limit_buckets[user_id]
    # Prune old entries
    times[:] = [t for t in times if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(times) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    times.append(now)
    return True

CLEANUP_ON_COMMANDS = {"/clean_on", "/bersih_on", "/hapus_on"}
CLEANUP_OFF_COMMANDS = {"/clean_off", "/bersih_off", "/hapus_off"}
CLEANUP_STATUS_COMMANDS = {"/clean_status", "/bersih_status"}
CLEANUP_OLD_COMMANDS = {"/hapus_lama", "/clean_old", "/bersih_lama"}
CLEANUP_BOT_OLD_COMMANDS = {"/hapus_bot_lama", "/clean_bot_old", "/bersih_bot_lama"}
CLEANUP_REPLY_COMMANDS = {"/hapus_ini", "/delete_this"}
CLEANUP_COMMANDS = (
    CLEANUP_ON_COMMANDS
    | CLEANUP_OFF_COMMANDS
    | CLEANUP_STATUS_COMMANDS
    | CLEANUP_OLD_COMMANDS
    | CLEANUP_BOT_OLD_COMMANDS
    | CLEANUP_REPLY_COMMANDS
)


def command_base(text: str) -> str:
    first_word = (text or "").split(maxsplit=1)[0].lower()
    return first_word.split("@", 1)[0]


def record_cleanup_candidate(message: Message) -> None:
    if should_keep_message(message):
        return

    record_cleanup_message(
        message.chat.id,
        message.message_thread_id,
        message.message_id,
        "user",
    )


def message_has_link(message: Message) -> bool:
    text = message.text or message.caption or ""
    if re.search(URL_REGEX, text):
        return True

    for entity in (message.entities or []) + (message.caption_entities or []):
        if entity.type in {"url", "text_link"}:
            return True

    return False


def message_has_kept_media(message: Message) -> bool:
    return bool(
        message.photo
        or message.video
        or message.animation
        or message.video_note
        or message.document
    )


def should_keep_message(message: Message) -> bool:
    if message_has_link(message) or message_has_kept_media(message):
        return True

    text = (message.text or "").split(maxsplit=1)[0].lower()
    if text in CLEANUP_COMMANDS:
        return False

    return False


async def delete_message_later(message: Message, delay_seconds: float = 0) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    try:
        await message.delete()
        mark_cleanup_message_deleted(message.chat.id, message.message_id)
    except Exception as exc:
        logger.warning("delete message failed chat_id=%s message_id=%s error=%s", message.chat.id, message.message_id, str(exc)[:160])


async def send_temporary_reply(message: Message, text: str, delay_seconds: float = 8) -> None:
    reply = await message.reply(text)
    record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
    if is_cleanup_enabled(message.chat.id, message.message_thread_id):
        asyncio.create_task(delete_message_later(reply, delay_seconds))


async def is_user_admin(message: Message) -> bool:
    if message.chat.type == "private":
        return True

    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True

    if not message.from_user:
        return False

    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in {"creator", "administrator"}
    except Exception as exc:
        logger.warning("admin check failed chat_id=%s user_id=%s error=%s", message.chat.id, message.from_user.id, str(exc)[:160])
        return False


async def bot_delete_permission_text(message: Message) -> str:
    if message.chat.type == "private":
        return "private chat"

    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(message.chat.id, me.id)
        can_delete = bool(
            member.status == "creator"
            or getattr(member, "can_delete_messages", False)
        )
        return "OK" if can_delete else "BELUM ADA izin Delete messages"
    except Exception as exc:
        logger.warning("bot permission check failed chat_id=%s error=%s", message.chat.id, str(exc)[:160])
        return "gagal dicek"


def cleanup_old_limit(text: str, default: int = 50, maximum: int = 100) -> int:
    parts = (text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return default

    return max(1, min(int(parts[1]), maximum))


def cleanup_old_all_topics(text: str) -> bool:
    parts = (text or "").lower().split()
    return any(part in {"all", "semua", "global"} for part in parts[1:])


async def delete_replied_message(message: Message) -> tuple[bool, str]:
    if not message.reply_to_message:
        return False, "Reply dulu ke pesan bot yang mau dihapus, lalu kirim /hapus_ini."

    target = message.reply_to_message
    me = await bot.get_me()
    if target.from_user and target.from_user.id != me.id:
        return False, "Pesan yang direply bukan pesan bot ini."

    try:
        await bot.delete_message(message.chat.id, target.message_id)
        mark_cleanup_message_deleted(message.chat.id, target.message_id)
        return True, "Pesan bot yang direply sudah dihapus."
    except Exception as exc:
        logger.warning(
            "delete replied message failed chat_id=%s message_id=%s error=%s",
            message.chat.id,
            target.message_id,
            str(exc)[:160],
        )
        return False, "Gagal hapus pesan yang direply. Cek izin delete/admin bot."




@dp.message(F.document)
async def handle_cookie_upload(message: Message):
    """Upload file cookie via Telegram. Caption nyebut platform: x/ig/tiktok/yt/fb."""
    if not await is_user_admin(message):
        return

    doc = message.document
    caption = (message.caption or "").strip()
    name_hint = (doc.file_name or "").lower()

    is_cookie_intent = (
        "cookie" in caption.lower()
        or "cookie" in name_hint
        or platform_from_text(caption) is not None
    )
    if not is_cookie_intent:
        return

    target_file = platform_from_text(caption) or platform_from_text(name_hint)
    if not target_file:
        await send_temporary_reply(
            message,
            "Sebut platform-nya bang di caption: x, ig, tiktok, yt, atau fb.\n"
            "Contoh caption: cookie ig",
            delay_seconds=15,
        )
        return

    if (doc.file_size or 0) > 2_000_000:
        await send_temporary_reply(message, "File cookie kegedean (>2MB). Cek lagi bang.", 12)
        return

    try:
        file = await bot.get_file(doc.file_id)
        buffer = await bot.download_file(file.file_path)
        raw = buffer.read()
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.exception("cookie download failed")
        await send_temporary_reply(message, f"Gagal ambil file cookie: {exc}", 12)
        return

    ok, info = validate_cookie_text(text)
    if not ok:
        await send_temporary_reply(message, f"Cookie ditolak: {info}", 12)
        return

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    dest = COOKIES_DIR / target_file
    try:
        dest.write_text(text, encoding="utf-8")
    except Exception as exc:
        logger.exception("cookie save failed")
        await send_temporary_reply(message, f"Gagal simpan cookie: {exc}", 12)
        return

    logger.info(
        "cookie saved platform_file=%s bytes=%s by=%s",
        target_file,
        len(text),
        message.from_user.id if message.from_user else "-",
    )
    asyncio.create_task(delete_message_later(message, 1))
    await send_temporary_reply(
        message,
        f"Cookie {target_file} ({info}) udah kesimpen ke folder cookies/. "
        "Pesan upload tadi gue hapus biar aman.",
        delay_seconds=12,
    )


@dp.message(F.text.regexp(r"^/(status|cookies|cookie_status)(@\w+)?$"))
async def handle_status(message: Message):
    if not await is_user_admin(message):
        reply = await message.reply("Command ini cuma buat admin.")
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 8))
        return

    worker_line = "Worker: \u274c gak kebaca"
    cookie_lines = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                WORKER_HEALTH_URL, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    worker_line = f"Worker: \u2705 online (queue: {data.get('queue_size', 0)})"
                    loaded = data.get("cookies_loaded", {})
                    for plat in ("x", "instagram", "tiktok", "youtube", "facebook"):
                        mark = "\u2705" if loaded.get(plat) else "\u2014"
                        cookie_lines.append(f"  {mark} {plat}")
                    if not data.get("tagger", True):
                        worker_line += "\nTagger: \u26a0\ufe0f gak ketemu"
                else:
                    worker_line = f"Worker: \u26a0\ufe0f status {resp.status}"
    except Exception:
        worker_line = "Worker: \u274c offline / gak respon"

    delete_permission = await bot_delete_permission_text(message)
    clean_status = (
        "ON" if is_cleanup_enabled(message.chat.id, message.message_thread_id) else "OFF"
    )

    cookie_block = "\n".join(cookie_lines) if cookie_lines else "  (worker offline)"
    text = (
        "⚡ Status Zervis Bot\n\n"
        f"{worker_line}\n"
        f"Clean mode (sini): {clean_status}\n"
        f"Delete permission: {delete_permission}\n\n"
        "Cookies ke-load:\n"
        f"{cookie_block}\n\n"
        "💡 Panduan cookies: ketik /cookie_help"
    )
    await send_temporary_reply(message, text, delay_seconds=30)


@dp.message(F.text.regexp(r"^/(cookie_help|panduan_cookie)(@\w+)?$"))
async def handle_cookie_help(message: Message):
    if not await is_user_admin(message):
        reply = await message.reply("Command ini cuma buat admin.")
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 8))
        return

    text = (
        "📖 *Panduan Setup Cookies*\n\n"
        "Cookie dibutuhkan untuk mengunduh konten dari akun private, restricted, atau berbatas umur.\n\n"
        "*Langkah 1: Dapatkan Ekstensi Browser*\n"
        "Pasang ekstensi pengekspor cookie format Netscape di browser Anda:\n"
        "• Chrome: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/ccolpedggfffedjfnhhcoedbnicgfkee)\n"
        "• Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)\n\n"
        "*Langkah 2: Ekspor Cookie dari Browser*\n"
        "1. Login ke platform target (x.com, instagram.com, dll) di browser.\n"
        "2. Buka situs tersebut, klik ikon ekstensi lalu pilih *Export* untuk menyimpan file `.txt` atau menyalin teks cookie.\n\n"
        "*Langkah 3: Pasang Cookie ke Bot*\n"
        "Pilih salah satu cara berikut:\n"
        "• *Lewat Chat Telegram (Paling Praktis):*\n"
        "  Kirim file `.txt` cookie tersebut ke chat bot ini dengan caption:\n"
        "  `cookie [platform]` (Contoh: `cookie ig`, `cookie x`, `cookie tiktok`)\n"
        "  _Pesan upload Anda akan otomatis dihapus bot demi keamanan._\n"
        "• *Lewat Dashboard Web:*\n"
        "  Buka dashboard di browser Anda (`http://127.0.0.1:3000/dashboard`), lalu gunakan tombol *Upload* atau *Paste Text*."
    )
    reply = await message.reply(text, parse_mode="Markdown", disable_web_page_preview=True)
    record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
    if is_cleanup_enabled(message.chat.id, message.message_thread_id):
        asyncio.create_task(delete_message_later(reply, 60))
        asyncio.create_task(delete_message_later(message, 1))


@dp.message(F.forum_topic_created)
async def save_new_topic(message: Message):
    topic_name = message.forum_topic_created.name
    thread_id = message.message_thread_id
    chat_id = message.chat.id
    topics_file = Path(__file__).resolve().parent / "topics.json"

    if topics_file.exists():
        with open(topics_file, "r", encoding="utf-8") as f:
            try:
                topics = json.load(f)
            except Exception:
                topics = {}
    else:
        topics = {}

    topics[f"{chat_id}:{thread_id}"] = topic_name

    with open(topics_file, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)


@dp.message(F.text.regexp(r"^/(clean_on|bersih_on|hapus_on|clean_off|bersih_off|hapus_off|clean_status|bersih_status|hapus_lama|clean_old|bersih_lama|hapus_bot_lama|clean_bot_old|bersih_bot_lama|hapus_ini|delete_this)(@\w+)?(?:\s+\d{1,3})?(?:\s+(all|semua|global))?$"))
async def handle_cleanup_command(message: Message):
    command = command_base(message.text or "")

    if not await is_user_admin(message):
        reply = await message.reply("Command ini cuma bisa dipakai admin grup.")
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 8))
        return

    if command in CLEANUP_ON_COMMANDS:
        set_cleanup_enabled(message.chat.id, message.message_thread_id, True)
        reply = await message.reply(
            "Clean mode ON. Teks biasa/status/error akan dihapus; media dan link tetap aman."
        )
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 8))
        asyncio.create_task(delete_message_later(message, 1))
        return

    if command in CLEANUP_OFF_COMMANDS:
        set_cleanup_enabled(message.chat.id, message.message_thread_id, False)
        reply = await message.reply("Clean mode OFF.")
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 8))
        asyncio.create_task(delete_message_later(message, 1))
        return

    if command in CLEANUP_OLD_COMMANDS:
        limit = cleanup_old_limit(message.text or "")
        deleted, failed = await delete_old_cleanup_messages(message, limit)
        reply = await message.reply(
            f"Hapus lama selesai. Terhapus: {deleted}. Gagal: {failed}."
        )
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 10))
        asyncio.create_task(delete_message_later(message, 1))
        return

    if command in CLEANUP_BOT_OLD_COMMANDS:
        limit = cleanup_old_limit(message.text or "")
        all_topics = cleanup_old_all_topics(message.text or "")
        deleted, failed = await delete_old_cleanup_messages(
            message,
            limit,
            sender="bot",
            all_topics=all_topics,
        )
        scope = "semua topic grup ini" if all_topics else "topic ini"
        reply = await message.reply(
            f"Hapus pesan bot lama ({scope}) selesai. Terhapus: {deleted}. Gagal: {failed}."
        )
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 10))
        asyncio.create_task(delete_message_later(message, 1))
        return

    if command in CLEANUP_REPLY_COMMANDS:
        ok, text = await delete_replied_message(message)
        reply = await message.reply(text)
        record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
        asyncio.create_task(delete_message_later(reply, 10))
        if ok:
            asyncio.create_task(delete_message_later(message, 1))
        return

    status = "ON" if is_cleanup_enabled(message.chat.id, message.message_thread_id) else "OFF"
    delete_permission = await bot_delete_permission_text(message)
    reply = await message.reply(
        f"Clean mode: {status}\n"
        f"Delete permission: {delete_permission}"
    )
    record_bot_cleanup_message(reply.chat.id, reply.message_thread_id, reply.message_id)
    asyncio.create_task(delete_message_later(reply, 8))
    asyncio.create_task(delete_message_later(message, 1))


async def delete_old_cleanup_messages(
    message: Message,
    limit: int,
    sender: str = "user",
    all_topics: bool = False,
) -> tuple[int, int]:
    message_ids = get_cleanup_candidates(
        message.chat.id,
        message.message_thread_id,
        limit,
        sender,
        all_topics,
    )
    deleted = 0
    failed = 0

    for msg_id in message_ids:
        try:
            await bot.delete_message(message.chat.id, msg_id)
            mark_cleanup_message_deleted(message.chat.id, msg_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            failed += 1
            logger.warning(
                "delete old message failed chat_id=%s message_id=%s error=%s",
                message.chat.id,
                msg_id,
                str(exc)[:160],
            )

    return deleted, failed


@dp.message(F.text.in_({"/where", "/topic", "/id"}))
async def show_current_topic(message: Message):
    await send_temporary_reply(
        message,
        "Info lokasi pesan:\n"
        f"chat_id: {message.chat.id}\n"
        f"group: {message.chat.title or message.chat.id}\n"
        f"message_thread_id: {message.message_thread_id or 'General/None'}"
    )


@dp.message(F.text.regexp(URL_REGEX))
async def handle_media_link(message: Message):
    user_id = message.from_user.id if message.from_user else message.chat.id

    if not check_rate_limit(user_id):
        await send_temporary_reply(
            message,
            "Rate limit: maksimal 5 link per menit. Tunggu sebentar ya.",
            delay_seconds=10,
        )
        return

    text = message.text or ""
    urls = [normalize_url(match.group(0)) for match in re.finditer(URL_REGEX, text)]
    original_url = next((url for url in urls if is_supported_url(url)), None)

    if not original_url:
        return

    await send_temporary_reply(message, "Saya cek dulu media dari link ini...")
    logger.info(
        "detected url chat_id=%s thread_id=%s url=%s",
        message.chat.id,
        message.message_thread_id,
        original_url,
    )

    payload = {
        "chat_id": message.chat.id,
        "group_name": message.chat.title or str(message.chat.id),
        "message_thread_id": message.message_thread_id,
        "tweet_id": media_id_from_url(original_url),
        "original_url": original_url,
        "user_tags": extract_user_tags(text),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENCLAW_WORKER_URL, json=payload) as resp:
                if resp.status != 200:
                    logger.error("worker failed status=%s url=%s", resp.status, original_url)
                    await send_temporary_reply(
                        message,
                        "Worker gagal memproses link. Coba cek log OpenClaw/worker."
                    )
    except Exception as exc:
        logger.exception("worker connection failed url=%s", original_url)
        await send_temporary_reply(message, f"Gagal menghubungi worker: {exc}")


@dp.message()
async def cleanup_plain_message(message: Message):
    await cleanup_message_if_enabled(message)


@dp.channel_post()
async def cleanup_plain_channel_post(message: Message):
    await cleanup_message_if_enabled(message)


async def cleanup_message_if_enabled(message: Message):
    if should_keep_message(message):
        return

    record_cleanup_candidate(message)

    if not is_cleanup_enabled(message.chat.id, message.message_thread_id):
        return

    await delete_message_later(message)


async def main():
    init_message_log_table()
    acquire_bot_lock()
    logger.info("bot polling started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
