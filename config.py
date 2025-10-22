import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")

# Кэш
CACHE_REFILL_SIZE = int(os.getenv("CACHE_REFILL_SIZE"))
CACHE_TTL         = int(os.getenv("CACHE_TTL"))
CACHE_MAX_KEYS    = int(os.getenv("CACHE_MAX_KEYS"))
CACHE_MAX_PAGES   = int(os.getenv("CACHE_MAX_PAGES"))

# Сеть/агент/прокси
USER_AGENT = os.getenv("USER_AGENT", "FurryTuesdayBot/1.0 (by @maksaucer)")
PROXY_URL  = os.getenv("PROXY_URL", "").strip()

# Gelbooru API (опционально, чтобы видеть NSFW)
GELBOORU_USER_ID = os.getenv("GELBOORU_USER_ID")
GELBOORU_API_KEY = os.getenv("GELBOORU_API_KEY")

# (если используешь БД)
DATABASE_URL = os.getenv("DATABASE_URL")