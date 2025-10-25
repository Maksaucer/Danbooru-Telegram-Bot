# database/filters.py
from database import get_db_pool

async def get_filters(user_id: int) -> list[str]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT filters FROM users WHERE telegram_id = $1", user_id)
        return row["filters"] if row and row["filters"] else []

async def add_filter(user_id: int, tag: str):
    if not isinstance(tag, str):
        raise ValueError("Тег должен быть строкой")
    tag = tag.lower()
    exclusive = {"sfw": "nsfw", "nsfw": "sfw"}.get(tag)

    pool = get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if exclusive:
                await conn.execute(
                    "UPDATE users SET filters = array_remove(filters, $1) WHERE telegram_id = $2",
                    exclusive, user_id
                )
            await conn.execute(
                """
                UPDATE users
                SET filters = ARRAY(SELECT DISTINCT unnest(filters || $1::text[]))
                WHERE telegram_id = $2
                """,
                [tag], user_id
            )

async def remove_filter(user_id: int, tag: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET filters = ARRAY(SELECT unnest(filters) EXCEPT SELECT $1) WHERE telegram_id = $2",
            tag, user_id
        )