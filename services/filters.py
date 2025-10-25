from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.filters import get_filters, add_filter, remove_filter

async def get_filters_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    filters = await get_filters(user_id)
    nsfw_status = "✅ ОТОБРАЖАЕТСЯ" if "nsfw" in filters else "❌ НЕ ОТОБРАЖАЕТСЯ"
    sfw_status = "✅ ОТОБРАЖАЕТСЯ" if "sfw" in filters else "❌ НЕ ОТОБРАЖАЕТСЯ"
    male_status = "✅ ОТОБРАЖАЕТСЯ" if "gay" in filters else "❌ НЕ ОТОБРАЖАЕТСЯ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
            InlineKeyboardButton(text=f"🚫 NSFW: {nsfw_status}", callback_data="toggle_nsfw"),
            InlineKeyboardButton(text=f"🚫 SFW: {sfw_status}", callback_data="toggle_sfw"),
            InlineKeyboardButton(text=f"🚫 GAY: {male_status}", callback_data="toggle_gay"),
            ]
        ]
    )

def get_rating_label(rating: str) -> str:
    r = (rating or "").lower()
    return {"s": "✅ Safe", "q": "⚠️ Questionable", "e": "🔞 Explicit"}.get(r, "❔ Unknown")

def _extract_ext(post: dict) -> str:
    file = post.get("file") or {}
    ext = (file.get("ext") or "").lower()
    if ext:
        return ext
    url = (file.get("url") or post.get("file_url") or "").lower()
    if "." in url:
        ext = url.rsplit(".", 1)[-1].split("?")[0]
    return ext or ""

def _extract_tags_set(post: dict) -> set[str]:
    t = post.get("tags")
    tags: set[str] = set()
    # e621-подобный: dict групп
    if isinstance(t, dict):
        for v in t.values():
            if isinstance(v, list):
                tags.update(x.lower() for x in v)
    # строки (gelbooru xml/json без нормализации)
    if isinstance(t, str):
        tags.update(x.lower() for x in t.split() if x)
    # запасной путь
    tag_string = post.get("tag_string")
    if isinstance(tag_string, str):
        tags.update(x.lower() for x in tag_string.split() if x)
    return tags

def is_post_allowed(post: dict, filters: list[str]) -> bool:
    fset = {f.lower() for f in (filters or [])}
    allowed_ext = {"jpg", "jpeg", "png", "gif", "webp", "mp4", "webm"}

    if _extract_ext(post) not in allowed_ext:
        return False

    tags = _extract_tags_set(post)

    if {"gore", "feces", "urine", "diaper", "pregnant"} & tags:
        return False

    if "sfw" in fset:
        if (post.get("rating") or "").lower() == "s":
            return False
    elif "nsfw" in fset:
        if (post.get("rating") or "").lower() in {"e", "q"}:
            return False

    if ("gay" in fset) and ("1girl" not in tags):
        return False

    if fset & tags:
        return False

    return True