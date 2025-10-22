# parsers/gelbooru.py
import logging
from typing import List, Dict, Any
from urllib.parse import urlencode
from aiohttp import ClientSession, ClientTimeout
from aiohttp_socks import ProxyConnector
import xml.etree.ElementTree as ET

from config import PROXY_URL, USER_AGENT, GELBOORU_USER_ID, GELBOORU_API_KEY

BASE_URL = "https://gelbooru.com/index.php"
AUTHED = bool(GELBOORU_USER_ID and GELBOORU_API_KEY)

def _make_session() -> ClientSession:
    if not PROXY_URL or not PROXY_URL.startswith(("socks5://", "socks5h://", "socks4://", "socks4a://")):
        raise RuntimeError("PROXY_URL must be socks5/socks4 URL (set in .env)")
    connector = ProxyConnector.from_url(PROXY_URL, rdns=True)
    timeout = ClientTimeout(total=20, connect=10, sock_read=15)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/*;q=0.9,*/*;q=0.8",
        "Referer": "https://gelbooru.com/",
    }
    return ClientSession(connector=connector, timeout=timeout, headers=headers)

def _base_params(json_mode: bool) -> Dict[str, Any]:
    p: Dict[str, Any] = {"page": "dapi", "s": "post", "q": "index"}
    if json_mode:
        p["json"] = 1
    if AUTHED:
        p["user_id"] = GELBOORU_USER_ID
        p["api_key"] = GELBOORU_API_KEY
    return p

def _norm_ext(url: str, fallback: str = "") -> str:
    try:
        ext = url.rsplit(".", 1)[-1].lower()
        if "/" in ext or "?" in ext:
            return fallback
        return ext
    except Exception:
        return fallback

def _normalize_post(p: Dict[str, Any]) -> Dict[str, Any]:
    file_url = p.get("file_url") or p.get("sample_url") or ""
    ext = (p.get("file_ext") or _norm_ext(file_url) or "").lower()

    r_raw = (p.get("rating") or "s").lower()
    rating_map = {"safe": "s", "s": "s", "questionable": "q", "q": "q", "explicit": "e", "e": "e"}
    rating = rating_map.get(r_raw, "s")

    tags_val = p.get("tags") or []
    if isinstance(tags_val, str):
        tags_list = [t for t in tags_val.split() if t]
    elif isinstance(tags_val, list):
        tags_list = [str(t) for t in tags_val if t]
    else:
        tags_list = []

    page_url = f"https://gelbooru.com/index.php?page=post&s=view&id={p.get('id')}"
    created_at = p.get("created_at")

    return {
        "id": str(p.get("id")),
        "file": {"url": file_url, "ext": ext},
        "rating": rating,                   # всегда s/q/e
        "tags": {"general": tags_list},     # единый вид
        "page_url": page_url,
        "created_at": created_at,
    }

def _parse_xml_posts(xml_text: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
        result: List[Dict[str, Any]] = []
        for node in root.findall("post"):
            d = dict(node.attrib)
            result.append(d)
        return result
    except Exception as e:
        logging.exception("Gelbooru XML parse error: %s", e)
        return []

async def _request(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    json_mode = AUTHED
    q = {**_base_params(json_mode), **params}
    url = f"{BASE_URL}?{urlencode(q, doseq=True)}"
    async with _make_session() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    if json_mode:
                        data = await resp.json(content_type=None)
                        posts = data.get("post") or data.get("posts") or data
                        if isinstance(posts, dict):
                            posts = posts.get("post") or []
                        return [p for p in (posts or []) if isinstance(p, dict)]
                    text = await resp.text()
                    return _parse_xml_posts(text)

                # fallback JSON->XML при 401/403
                if resp.status in (401, 403) and json_mode:
                    text = await resp.text()
                    logging.warning("Gelbooru %s on JSON, fallback to XML. Body: %s", resp.status, text[:300])
                    q_xml = {**_base_params(False), **params}
                    url_xml = f"{BASE_URL}?{urlencode(q_xml, doseq=True)}"
                    async with session.get(url_xml) as resp2:
                        if resp2.status == 200:
                            txt = await resp2.text()
                            return _parse_xml_posts(txt)
                        txt = await resp2.text()
                        logging.error("Gelbooru %s on XML as well: %s", resp2.status, txt[:300])
                        return []

                text = await resp.text()
                logging.error("Gelbooru %s: %s", resp.status, text[:500])
                return []
        except Exception as e:
            logging.exception("Gelbooru request failed: %s", e)
            return []

async def fetch_by_tags(tags: List[str], limit: int = 50, pid: int | None = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit, "tags": " ".join(tags)}
    if pid is not None:
        params["pid"] = pid  # номер страницы (0,1,2,…)
    raw = await _request(params)
    return [_normalize_post(p) for p in raw if p.get("file_url") or p.get("sample_url")]

async def fetch_random(limit: int = 50) -> List[Dict[str, Any]]:
    return await fetch_by_tags(tags=["sort:random"], limit=limit)

async def fetch_top(limit: int = 50) -> List[Dict[str, Any]]:
    return await fetch_by_tags(tags=["sort:score"], limit=limit)