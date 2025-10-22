from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.filters import get_filters, add_filter, remove_filter

async def get_filters_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    filters = await get_filters(user_id)
    nsfw_status = "✅ ВКЛ" if "nsfw" in filters else "❌ ВЫКЛ"
    male_status = "✅ ВКЛ" if "gay" in filters else "❌ ВЫКЛ"
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=f"🚫 NSFW: {nsfw_status}", callback_data="toggle_nsfw"),
            InlineKeyboardButton(text=f"🚫 GAY: {male_status}", callback_data="toggle_gay"),
        ]]
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

    # 0) формат
    if _extract_ext(post) not in allowed_ext:
        return False

    # 1) теги
    tags = _extract_tags_set(post)

    # 2) жёсткие баны
    if {"gore", "feces", "urine"} & tags:
        return False

    if not fset:
        return True

    # 3) рейтинг: при включённом фильтре nsfw отсекаем явный NSFW (e/q)
    rating = (post.get("rating") or "").lower()
    if "nsfw" in fset and rating in {"e", "q"}:
        return False

    # 4) грубая эвристика против male-only при фильтре "gay"
    if "gay" in fset and ("1boy" in tags and "1girl" not in tags):
        return False

    # 5) пользовательские минус‑теги (если вдруг хранишь реальные теги в filters)
    if fset & tags:
        return False

    return True