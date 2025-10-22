# services/images.py
import logging
from aiogram import Bot

from database.users import get_username, load_users
from database.filters import get_filters
from services.filters import is_post_allowed, get_rating_label
from services.cache import cache
from parsers.gelbooru import fetch_top  # «топ», дальше режем период/фильтры

FURRY_TUESDAY_CAPTION = "" # Пока никакой 

async def send_media(bot: Bot, user_id: int, file_url: str, file_ext: str, caption: str):
    try:
        ext = file_ext.lower()
        if ext in ["jpg", "jpeg", "png", "webp"]:
            await bot.send_photo(user_id, file_url, caption=caption)
        elif ext in ["gif"]:
            await bot.send_animation(user_id, file_url, caption=caption)
        elif ext in ["webm", "mp4"]:
            await bot.send_video(user_id, file_url, caption=caption)
        else:
            logging.warning(f"Unsupported file type: {file_ext}")
            await bot.send_message(user_id, f"⚠️ Тип файла {file_ext} не поддерживается Telegram.")
    except Exception as e:
        logging.error(f"Send media failed ({file_ext}): {e}")
        await bot.send_message(user_id, "❌ Произошла ошибка при отправке медиафайла.")

async def send_random_image(bot: Bot, user_id: int):
    filters = await get_filters(user_id)
    username = await get_username(user_id)

    for _ in range(10):
        post = await cache.get_post(user_filters=filters, random_order=True)
        if not post:
            await bot.send_message(user_id, "😞 Не удалось найти подходящую картинку по вашим фильтрам.")
            return
        file_url = post["file"]["url"]
        file_ext = post["file"]["ext"]
        post_url = post.get("page_url", "")
        rating = get_rating_label(post.get("rating", ""))
        caption = f"{rating}\n{post_url}"
        await send_media(bot, user_id, file_url, file_ext, caption)
        logging.info(f"✅ Отправлен пост {post['id']} пользователю {user_id} - @{username} (рейтинг: {rating})")
        return

    await bot.send_message(user_id, "😞 Не удалось найти подходящую случайную картинку по вашим фильтрам.")


async def send_image(bot: Bot, user_id: int, period: str = "week", caption: str = ""):
    filters = await get_filters(user_id)
    username = await get_username(user_id)

    # Берём пост через общий кэш (он сам добавит rating:safe при отсутствии ключей)
    post = await cache.get_post(user_filters=filters, period=period, random_order=False)
    if not post:
        await bot.send_message(user_id, "😞 Не удалось найти подходящую картинку по вашим фильтрам.")
        return
    file_url = post["file"]["url"]
    file_ext = post["file"]["ext"]
    post_url = post.get("page_url", "")
    rating = get_rating_label(post.get("rating", ""))

    full_caption = caption + f"{rating}\n{post_url}"
    await send_media(bot, user_id, file_url, file_ext, full_caption)
    logging.info(f"✅ Отправлен пост {post['id']} пользователю {user_id} - @{username} (рейтинг: {rating})")
    if caption == FURRY_TUESDAY_CAPTION:
        await bot.send_message(user_id, "😞 Фурри вторник отменён — у вас слишком строгие фильтры или запрещён NSFW.")
    else:
        await bot.send_message(user_id, "😞 Не удалось найти подходящую картинку по вашим фильтрам.")

async def send_image_toeveryone(bot: Bot, period: str = "week"):
    users = await load_users()
    for user_id in users:
        try:
            await send_image(bot, user_id, period=period, caption=FURRY_TUESDAY_CAPTION)
        except Exception as e:
            logging.warning(f"❌ Не удалось отправить сообщение пользователю {user_id}: {e}")