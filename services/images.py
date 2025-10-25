import logging
import mimetypes
from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiohttp import ClientSession, ClientTimeout
from aiohttp_socks import ProxyConnector

from config import PROXY_URL, USER_AGENT
from database.users import get_username, load_users
from database.filters import get_filters
from services.filters import get_rating_label
from services.cache import cache

FURRY_TUESDAY_CAPTION = ""
MAX_PHOTO_MB = 10


def _guess_ext(ext: str, content_type: str) -> str:
    ext = (ext or "").lower()
    if not ext and content_type:
        ext = (mimetypes.guess_extension(content_type.split(";")[0].strip()) or "").lstrip(".")
    return ext or "jpg"


async def _download(url: str) -> tuple[bytes, int, str]:
    connector = ProxyConnector.from_url(PROXY_URL, rdns=True)
    timeout = ClientTimeout(total=45, connect=12, sock_read=40)
    headers = {"User-Agent": USER_AGENT, "Referer": "https://gelbooru.com/"}
    async with ClientSession(connector=connector, timeout=timeout, headers=headers) as s:
        async with s.get(url) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "") or ""
            decl = int(r.headers.get("Content-Length") or 0)
            data = await r.read()
            size = decl or len(data)
            return data, size, ctype


async def send_media(bot: Bot, user_id: int, file_url: str, file_ext: str, caption: str):
    try:
        data, size, ctype = await _download(file_url)
        ext = _guess_ext(file_ext, ctype)
        buf = BufferedInputFile(data, filename=f"file.{ext}")
        mb = size / (1024 * 1024)
        if ext in {"jpg", "jpeg", "png", "webp"} and mb <= MAX_PHOTO_MB:
            await bot.send_photo(user_id, buf, caption=caption)
            return
        if ext == "gif":
            await bot.send_animation(user_id, buf, caption=caption)
            return
        if ext == "mp4":
            await bot.send_video(user_id, buf, caption=caption)
            return
        await bot.send_document(user_id, buf, caption=caption)
    except Exception as e:
        logging.error(f"Send media failed ({file_ext}): {e}")
        try:
            await bot.send_document(user_id, file_url, caption=caption)
        except Exception:
            await bot.send_message(user_id, f"{caption}\n{file_url}")


async def send_random_image(bot: Bot, user_id: int):
    filters = await get_filters(user_id)
    username = await get_username(user_id)
    for _ in range(10):
        post = await cache.get_post(user_filters=filters, period="week", random_order=True)
        if not post:
            break
        file_url = post["file"]["url"]
        file_ext = post["file"]["ext"]
        post_url = post.get("page_url", "")
        rating = get_rating_label(post.get("rating", ""))
        caption = f"{rating}\n{post_url}"
        await send_media(bot, user_id, file_url, file_ext, caption)
        logging.info(f"Отправлен пост {post['id']} пользователю {user_id} - @{username} (рейтинг: {rating})")
        return
    await bot.send_message(user_id, "😞 Не удалось найти подходящую случайную картинку по вашим фильтрам.")


async def send_image(bot: Bot, user_id: int, period: str = "week", caption: str = ""):
    filters = await get_filters(user_id)
    username = await get_username(user_id)
    post = await cache.get_post(user_filters=filters, period=period, random_order=False)
    if not post:
        logging.info("Top by period returned nothing; fallback to random-order cache")
        post = await cache.get_post(user_filters=filters, period=period, random_order=True)
    if not post:
        await bot.send_message(user_id, "😞 Не удалось найти подходящую картинку по вашим фильтрам.")
        return
    file_url = post["file"]["url"]
    file_ext = post["file"]["ext"]
    post_url = post.get("page_url", "")
    rating = get_rating_label(post.get("rating", ""))
    full_caption = caption + f"{rating}\n{post_url}"
    await send_media(bot, user_id, file_url, file_ext, full_caption)
    logging.info(f"Отправлен пост {post['id']} пользователю {user_id} - @{username} (рейтинг: {rating})")


async def send_image_toeveryone(bot: Bot, period: str = "week"):
    users = await load_users()
    for user_id in users:
        try:
            await send_image(bot, user_id, period=period, caption=FURRY_TUESDAY_CAPTION)
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")      