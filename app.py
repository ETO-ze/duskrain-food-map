import os
import re
import json
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "food_map.db"

AMAP_WEB_SERVICE_KEY = os.getenv("AMAP_WEB_SERVICE_KEY", "").strip()
AMAP_JS_KEY = os.getenv("AMAP_JS_KEY", "").strip()
AMAP_SECURITY_CODE = os.getenv("AMAP_SECURITY_CODE", "").strip()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
DEVELOPER_SESSION_COOKIE = "duskrain_developer_session"
DEVELOPER_SESSION_HOURS = 24
INITIAL_DEVELOPER_PASSWORD = "123123"
PASSWORD_ITERATIONS = 310_000
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_FAILURES: dict[str, list[datetime]] = {}

DEFAULT_DEVELOPER_ACCOUNTS = (
    ("adminljz", "吕俊泽"),
    ("adminlxy", "李昕阳"),
    ("admingjdtddd", "果酱呆头大大大"),
    ("adminwyz", "王钰泽"),
    ("adminczk", "陈智鲲"),
    ("adminly", "雷洋"),
)

COMMON_CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉",
    "西安", "天津", "长沙", "郑州", "青岛", "宁波", "厦门", "福州", "无锡", "合肥",
    "佛山", "东莞", "珠海", "海口", "三亚", "香港", "澳门", "台北",
)

app = FastAPI(title="DuskRain Food Map")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class PlaceIn(BaseModel):
    map_provider: str = "amap"
    country_code: str = "CN"
    coordinate_system: str = "gcj02"
    provider_poi_id: str = ""
    name: str = Field(..., min_length=1, max_length=120)
    address: str = ""
    lng: float
    lat: float
    city: str = ""
    district: str = ""
    provider_category: str = ""
    phone: str = ""
    business_hours: str = ""
    amap_detail_url: str = ""
    provider_detail_url: str = ""
    my_category: str = ""
    my_categories: list[str] = Field(default_factory=list)
    rating: Optional[float] = Field(default=None, ge=0, le=10)
    rating_author: str = "吕俊泽"
    recommend_level: str = ""
    review_url: str = ""
    review_text: str = ""
    tags: str = ""
    note: str = ""
    visited_at: str = ""
    cover_image: str = ""
    image_urls: str = ""
    hide_images: bool = False
    is_public: bool = True


class Place(PlaceIn):
    id: int
    created_at: str
    updated_at: str


class DeveloperLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=48)
    password: str = Field(..., min_length=6, max_length=128)


class DeveloperPasswordChange(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeveloperAccountIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=48)
    author_name: str = Field(..., min_length=1, max_length=80)
    is_active: bool = True


class DeveloperAccountUpdate(DeveloperAccountIn):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


CATEGORY_SPLIT_RE = re.compile(r"\s*(?:[,，、|;/；]|\s+/\s+)\s*")


def normalize_category_values(
    values: Optional[list[Any]] = None,
    legacy_value: Any = "",
) -> list[str]:
    raw_values: list[Any] = list(values or [])
    if not raw_values and legacy_value not in (None, ""):
        raw_values = [legacy_value]
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for part in CATEGORY_SPLIT_RE.split(str(raw_value or "")):
            category = part.strip()[:40]
            key = category.casefold()
            if not category or key in seen:
                continue
            seen.add(key)
            result.append(category)
            if len(result) >= 12:
                return result
    return result


def decode_category_values(value: Any, legacy_value: Any = "") -> list[str]:
    parsed: list[Any] = []
    if isinstance(value, list):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            candidate = json.loads(value)
            if isinstance(candidate, list):
                parsed = candidate
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = [value]
    return normalize_category_values(parsed, legacy_value if not parsed else "")


def payload_category_values(payload: PlaceIn) -> list[str]:
    return normalize_category_values(payload.my_categories, payload.my_category)


def encode_category_values(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def db() -> Any:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def password_hash(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        PASSWORD_ITERATIONS,
    )
    return actual_salt.hex(), digest.hex()


def password_matches(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = password_hash(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_account(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "author_name": row["author_name"],
        "is_active": bool(row["is_active"]),
        "must_change_password": bool(row["must_change_password"]),
        "last_login_at": row["last_login_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def seed_developer_accounts(conn: sqlite3.Connection) -> None:
    now = utc_now()
    for username, author_name in DEFAULT_DEVELOPER_ACCOUNTS:
        exists = conn.execute(
            "SELECT 1 FROM developer_accounts WHERE lower(username) = lower(?)",
            (username,),
        ).fetchone()
        if exists:
            continue
        salt, digest = password_hash(INITIAL_DEVELOPER_PASSWORD)
        conn.execute(
            """
            INSERT INTO developer_accounts (
                username, author_name, password_salt, password_hash,
                must_change_password, is_active, last_login_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, 1, '', ?, ?)
            """,
            (username, author_name, salt, digest, now, now),
        )


def read_developer_account(request: Request, require_password_changed: bool = True) -> sqlite3.Row:
    token = request.cookies.get(DEVELOPER_SESSION_COOKIE, "")
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    now = utc_now()
    with db() as conn:
        conn.execute("DELETE FROM developer_sessions WHERE expires_at <= ?", (now,))
        row = conn.execute(
            """
            SELECT a.*
            FROM developer_sessions s
            JOIN developer_accounts a ON a.id = s.account_id
            WHERE s.token_hash = ? AND s.expires_at > ? AND a.is_active = 1
            LIMIT 1
            """,
            (session_token_hash(token), now),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE developer_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now, session_token_hash(token)),
            )
    if not row:
        raise HTTPException(status_code=401, detail="登录已失效")
    if require_password_changed and row["must_change_password"]:
        raise HTTPException(status_code=403, detail="请先修改初始密码")
    return row


PLACE_INFORMATION_FIELDS = (
    "address", "city", "district", "provider_category", "phone", "business_hours",
    "amap_detail_url", "provider_detail_url", "my_category", "rating",
    "recommend_level", "review_url", "review_text", "tags", "note", "visited_at",
    "cover_image", "image_urls",
)


def place_information_score(row: sqlite3.Row) -> int:
    item = dict(row)
    score = 0
    for field in PLACE_INFORMATION_FIELDS:
        value = item.get(field)
        if value is None or value == "":
            continue
        text = str(value).strip()
        if text:
            score += 10 + min(len(text), 100)
    score += max(0, len(decode_category_values(item.get("my_categories"), item.get("my_category"))) - 1) * 10
    return score


def remove_author_duplicates(conn: sqlite3.Connection) -> None:
    groups: dict[tuple[Any, ...], list[sqlite3.Row]] = {}
    rows = conn.execute("SELECT * FROM food_places ORDER BY id").fetchall()
    for row in rows:
        author = (row["rating_author"] or "吕俊泽").strip().lower()
        provider_poi_id = (row["provider_poi_id"] or "").strip()
        if provider_poi_id:
            key = ("poi", row["map_provider"] or "amap", provider_poi_id, author)
        else:
            name = (row["name"] or "").strip().lower()
            address = (row["address"] or "").strip().lower()
            if not name or not address:
                continue
            key = (
                "location",
                name,
                address,
                round(float(row["lng"]), 6),
                round(float(row["lat"]), 6),
                author,
            )
        groups.setdefault(key, []).append(row)

    for matches in groups.values():
        if len(matches) < 2:
            continue
        best = max(
            matches,
            key=lambda row: (
                place_information_score(row),
                row["updated_at"] or "",
                row["id"],
            ),
        )
        duplicate_ids = [row["id"] for row in matches if row["id"] != best["id"]]
        conn.executemany(
            "DELETE FROM food_places WHERE id = ?",
            [(place_id,) for place_id in duplicate_ids],
        )


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS food_places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                map_provider TEXT DEFAULT 'amap',
                country_code TEXT DEFAULT 'CN',
                coordinate_system TEXT DEFAULT 'gcj02',
                provider_poi_id TEXT DEFAULT '',
                name TEXT NOT NULL,
                address TEXT DEFAULT '',
                lng REAL NOT NULL,
                lat REAL NOT NULL,
                city TEXT DEFAULT '',
                district TEXT DEFAULT '',
                provider_category TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                business_hours TEXT DEFAULT '',
                amap_detail_url TEXT DEFAULT '',
                provider_detail_url TEXT DEFAULT '',
                my_category TEXT DEFAULT '',
                my_categories TEXT NOT NULL DEFAULT '[]',
                rating REAL,
                rating_author TEXT DEFAULT '吕俊泽',
                recommend_level TEXT DEFAULT '',
                review_url TEXT DEFAULT '',
                review_text TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                note TEXT DEFAULT '',
                visited_at TEXT DEFAULT '',
                cover_image TEXT DEFAULT '',
                image_urls TEXT DEFAULT '',
                hide_images INTEGER NOT NULL DEFAULT 0,
                is_public INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(food_places)").fetchall()
        }
        migrations = {
            "map_provider": "ALTER TABLE food_places ADD COLUMN map_provider TEXT DEFAULT 'amap'",
            "country_code": "ALTER TABLE food_places ADD COLUMN country_code TEXT DEFAULT 'CN'",
            "coordinate_system": "ALTER TABLE food_places ADD COLUMN coordinate_system TEXT DEFAULT 'gcj02'",
            "phone": "ALTER TABLE food_places ADD COLUMN phone TEXT DEFAULT ''",
            "business_hours": "ALTER TABLE food_places ADD COLUMN business_hours TEXT DEFAULT ''",
            "amap_detail_url": "ALTER TABLE food_places ADD COLUMN amap_detail_url TEXT DEFAULT ''",
            "provider_detail_url": "ALTER TABLE food_places ADD COLUMN provider_detail_url TEXT DEFAULT ''",
            "my_categories": "ALTER TABLE food_places ADD COLUMN my_categories TEXT NOT NULL DEFAULT '[]'",
            "rating_author": "ALTER TABLE food_places ADD COLUMN rating_author TEXT DEFAULT '吕俊泽'",
            "review_url": "ALTER TABLE food_places ADD COLUMN review_url TEXT DEFAULT ''",
            "review_text": "ALTER TABLE food_places ADD COLUMN review_text TEXT DEFAULT ''",
            "image_urls": "ALTER TABLE food_places ADD COLUMN image_urls TEXT DEFAULT ''",
            "hide_images": "ALTER TABLE food_places ADD COLUMN hide_images INTEGER NOT NULL DEFAULT 0",
        }
        for column, sql in migrations.items():
            if column not in existing_columns:
                conn.execute(sql)
        conn.execute(
            "UPDATE food_places SET rating_author = '吕俊泽' WHERE rating_author IS NULL OR trim(rating_author) = ''"
        )
        conn.execute(
            "UPDATE food_places SET map_provider = 'amap' WHERE map_provider IS NULL OR trim(map_provider) = ''"
        )
        conn.execute(
            "UPDATE food_places SET country_code = 'CN' WHERE country_code IS NULL OR trim(country_code) = ''"
        )
        conn.execute(
            "UPDATE food_places SET coordinate_system = 'gcj02' WHERE coordinate_system IS NULL OR trim(coordinate_system) = ''"
        )
        category_rows = conn.execute(
            "SELECT id, my_category, my_categories FROM food_places"
        ).fetchall()
        for row in category_rows:
            category_values = decode_category_values(row["my_categories"], row["my_category"])
            primary_category = category_values[0] if category_values else ""
            encoded_categories = encode_category_values(category_values)
            if row["my_category"] != primary_category or row["my_categories"] != encoded_categories:
                conn.execute(
                    "UPDATE food_places SET my_category = ?, my_categories = ? WHERE id = ?",
                    (primary_category, encoded_categories, row["id"]),
                )
        conn.execute(
            """
            UPDATE food_places
            SET provider_detail_url = amap_detail_url
            WHERE (provider_detail_url IS NULL OR trim(provider_detail_url) = '')
              AND amap_detail_url IS NOT NULL
              AND trim(amap_detail_url) != ''
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_food_places_public ON food_places(is_public)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_food_places_category ON food_places(my_category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_food_places_provider_poi ON food_places(provider_poi_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_food_places_map_provider ON food_places(map_provider)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                author_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_login_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES developer_accounts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_developer_sessions_account ON developer_sessions(account_id)"
        )
        seed_developer_accounts(conn)
        remove_author_duplicates(conn)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def row_to_place(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["is_public"] = bool(item["is_public"])
    item["hide_images"] = bool(item.get("hide_images", 0))
    item["rating_author"] = item.get("rating_author") or "吕俊泽"
    item["my_categories"] = decode_category_values(
        item.get("my_categories"),
        item.get("my_category", ""),
    )
    item["my_category"] = item["my_categories"][0] if item["my_categories"] else ""
    return item


def find_duplicate_place(
    conn: sqlite3.Connection, payload: PlaceIn, exclude_id: Optional[int] = None
) -> Optional[sqlite3.Row]:
    exclude_sql = ""
    exclude_params: list[Any] = []
    if exclude_id is not None:
        exclude_sql = " AND id != ?"
        exclude_params.append(exclude_id)

    provider_poi_id = payload.provider_poi_id.strip()
    map_provider = payload.map_provider.strip() or "amap"
    rating_author = payload.rating_author.strip() or "吕俊泽"
    if provider_poi_id:
        row = conn.execute(
            f"""
            SELECT * FROM food_places
            WHERE map_provider = ?
              AND provider_poi_id = ?
              AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
              {exclude_sql}
            LIMIT 1
            """,
            [map_provider, provider_poi_id, rating_author, *exclude_params],
        ).fetchone()
        if row:
            return row

    name = payload.name.strip()
    address = payload.address.strip()
    if name and address:
        row = conn.execute(
            f"""
            SELECT * FROM food_places
            WHERE lower(trim(name)) = lower(trim(?))
              AND lower(trim(address)) = lower(trim(?))
              AND abs(lng - ?) < 0.000001
              AND abs(lat - ?) < 0.000001
              AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
              {exclude_sql}
            LIMIT 1
            """,
            [name, address, payload.lng, payload.lat, rating_author, *exclude_params],
        ).fetchone()
        if row:
            return row
    return None


def duplicate_place_error(row: sqlite3.Row) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": "Place already exists",
            "existingId": row["id"],
            "existing": row_to_place(row),
        },
    )


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _poi_detail_url(poi_id: str, name: str, lng: float, lat: float) -> str:
    if lng and lat:
        return (
            "https://uri.amap.com/marker"
            f"?position={lng},{lat}&name={name}&src=duskrain&coordinate=gaode&callnative=0"
        )
    if poi_id:
        return f"https://ditu.amap.com/place/{poi_id}"
    return ""


def normalize_amap_poi(poi: dict[str, Any]) -> Optional[dict[str, Any]]:
    location = poi.get("location") or ""
    if "," not in location:
        return None
    lng_raw, lat_raw = location.split(",", 1)
    lng = float(lng_raw)
    lat = float(lat_raw)
    name = _string_value(poi.get("name"))
    poi_id = _string_value(poi.get("id"))
    biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
    open_time = (
        _string_value(biz_ext.get("opentime"))
        or _string_value(biz_ext.get("open_time"))
        or _string_value(poi.get("opentime"))
    )
    photos = poi.get("photos") if isinstance(poi.get("photos"), list) else []
    image_urls = []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        url = _string_value(photo.get("url"))
        if url:
            image_urls.append(url)

    return {
        "map_provider": "amap",
        "country_code": "CN",
        "coordinate_system": "gcj02",
        "provider_poi_id": poi_id,
        "name": name,
        "address": _string_value(poi.get("address")),
        "lng": lng,
        "lat": lat,
        "city": _string_value(poi.get("cityname")),
        "district": _string_value(poi.get("adname")),
        "provider_category": _string_value(poi.get("type")),
        "phone": _string_value(poi.get("tel")),
        "business_hours": open_time,
        "amap_detail_url": _poi_detail_url(poi_id, name, lng, lat),
        "provider_detail_url": _poi_detail_url(poi_id, name, lng, lat),
        "image_urls": "\n".join(image_urls),
        "cover_image": image_urls[0] if image_urls else "",
    }


def normalize_search(q: str, city: str) -> tuple[str, str]:
    keyword = " ".join(q.strip().split())
    normalized_city = city.strip()
    if normalized_city:
        return keyword, normalized_city

    for candidate in COMMON_CITIES:
        patterns = (
            rf"^{re.escape(candidate)}市?\s+(.+)$",
            rf"^(.+)\s+{re.escape(candidate)}市?$",
        )
        for pattern in patterns:
            match = re.match(pattern, keyword)
            if match:
                terms = [part for part in match.groups() if part]
                if terms:
                    return terms[0].strip(), candidate
    return keyword, normalized_city


def _search_match_text(value: Any) -> str:
    return re.sub(r"[\s·・.()（）\-_/]+", "", _string_value(value)).lower()


def _amap_poi_search_score(poi: dict[str, Any], keyword: str, city: str) -> int:
    query = _search_match_text(keyword)
    name = _search_match_text(poi.get("name"))
    address = _search_match_text(poi.get("address"))
    city_name = _search_match_text(poi.get("cityname"))
    score = 0
    if query and name == query:
        score += 1000
    elif query and query in name:
        score += 700
    elif query and len(name) >= 2 and name in query:
        score += 550
    elif query and query in address:
        score += 350
    if city and _search_match_text(city) in city_name:
        score += 80
    if _string_value(poi.get("type")).startswith("餐饮服务"):
        score += 20
    return score


def _has_strong_amap_match(pois: list[dict[str, Any]], keyword: str) -> bool:
    query = _search_match_text(keyword)
    if not query:
        return False
    return any(
        query in _search_match_text(poi.get("name"))
        or (
            len(_search_match_text(poi.get("name"))) >= 2
            and _search_match_text(poi.get("name")) in query
        )
        for poi in pois
    )


@app.get("/")
def public_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/admin/")
def admin_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/admin")
def admin_page_no_slash() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/developer/")
def developer_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/developer")
def developer_page_no_slash() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/review/{place_id}")
def review_page(place_id: int) -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/global/")
def global_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/global")
def global_page_no_slash() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now()}


@app.get("/api/config")
def config() -> dict[str, str]:
    return {
        "amapJsKey": AMAP_JS_KEY,
        "amapSecurityCode": AMAP_SECURITY_CODE,
        "googleMapsApiKey": GOOGLE_MAPS_API_KEY,
    }


@app.post("/api/developer/login")
def developer_login(
    payload: DeveloperLogin,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    username = payload.username.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    attempt_key = f"{client_ip}:{username}"
    cutoff = datetime.now(timezone.utc) - LOGIN_FAILURE_WINDOW
    failures = [attempt for attempt in LOGIN_FAILURES.get(attempt_key, []) if attempt > cutoff]
    if len(failures) >= LOGIN_FAILURE_LIMIT:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后重试")
    with db() as conn:
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE lower(username) = ? LIMIT 1",
            (username,),
        ).fetchone()
        if (
            not account
            or not account["is_active"]
            or not password_matches(
                payload.password,
                account["password_salt"],
                account["password_hash"],
            )
        ):
            failures.append(datetime.now(timezone.utc))
            LOGIN_FAILURES[attempt_key] = failures
            raise HTTPException(status_code=401, detail="账号或密码错误")
        LOGIN_FAILURES.pop(attempt_key, None)
        now = utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=DEVELOPER_SESSION_HOURS)).isoformat()
        token = secrets.token_urlsafe(32)
        conn.execute(
            """
            INSERT INTO developer_sessions (
                account_id, token_hash, expires_at, created_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (account["id"], session_token_hash(token), expires_at, now, now),
        )
        conn.execute(
            "UPDATE developer_accounts SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, account["id"]),
        )
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?",
            (account["id"],),
        ).fetchone()
    response.set_cookie(
        DEVELOPER_SESSION_COOKIE,
        token,
        max_age=DEVELOPER_SESSION_HOURS * 60 * 60,
        path="/food-map",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return public_account(account)


@app.get("/api/developer/session")
def developer_session(request: Request) -> dict[str, Any]:
    return public_account(read_developer_account(request, require_password_changed=False))


@app.post("/api/developer/logout")
def developer_logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(DEVELOPER_SESSION_COOKIE, "")
    if token:
        with db() as conn:
            conn.execute(
                "DELETE FROM developer_sessions WHERE token_hash = ?",
                (session_token_hash(token),),
            )
    response.delete_cookie(DEVELOPER_SESSION_COOKIE, path="/food-map")
    return {"ok": True}


@app.post("/api/developer/change-password")
def developer_change_password(
    payload: DeveloperPasswordChange,
    request: Request,
) -> dict[str, Any]:
    account = read_developer_account(request, require_password_changed=False)
    if not password_matches(
        payload.current_password,
        account["password_salt"],
        account["password_hash"],
    ):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.new_password == INITIAL_DEVELOPER_PASSWORD:
        raise HTTPException(status_code=400, detail="新密码不能继续使用初始密码")
    salt, digest = password_hash(payload.new_password)
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE developer_accounts
            SET password_salt = ?, password_hash = ?, must_change_password = 0, updated_at = ?
            WHERE id = ?
            """,
            (salt, digest, now, account["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?",
            (account["id"],),
        ).fetchone()
    return public_account(updated)


@app.get("/api/developer/places", response_model=list[Place])
def list_developer_places(request: Request) -> list[dict[str, Any]]:
    account = read_developer_account(request)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM food_places
            WHERE lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
            ORDER BY updated_at DESC
            """,
            (account["author_name"],),
        ).fetchall()
    return [row_to_place(row) for row in rows]


@app.post("/api/developer/places", response_model=Place)
def create_developer_place(payload: PlaceIn, request: Request) -> dict[str, Any]:
    account = read_developer_account(request)
    return create_place(payload.model_copy(update={"rating_author": account["author_name"]}))


def developer_owned_place(place_id: int, account: sqlite3.Row) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute(
            """
            SELECT * FROM food_places
            WHERE id = ?
              AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
            """,
            (place_id, account["author_name"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="店家不存在或不属于当前作者")
    return row


@app.put("/api/developer/places/{place_id}", response_model=Place)
def update_developer_place(
    place_id: int,
    payload: PlaceIn,
    request: Request,
) -> dict[str, Any]:
    account = read_developer_account(request)
    developer_owned_place(place_id, account)
    return update_place(
        place_id,
        payload.model_copy(update={"rating_author": account["author_name"]}),
    )


@app.delete("/api/developer/places/{place_id}")
def delete_developer_place(place_id: int, request: Request) -> dict[str, bool]:
    account = read_developer_account(request)
    developer_owned_place(place_id, account)
    return delete_place(place_id)


@app.get("/api/places", response_model=list[Place])
def list_public_places(
    category: str = "",
    recommend: str = "",
) -> list[dict[str, Any]]:
    clauses = ["is_public = 1"]
    params: list[Any] = []
    if recommend:
        clauses.append("recommend_level = ?")
        params.append(recommend)
    sql = "SELECT * FROM food_places WHERE " + " AND ".join(clauses)
    sql += " ORDER BY COALESCE(rating, 0) DESC, updated_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    items = [row_to_place(row) for row in rows]
    if category:
        items = [item for item in items if category in item["my_categories"]]
    return items


@app.get("/api/places/{place_id}", response_model=Place)
def get_public_place(place_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM food_places WHERE id = ? AND is_public = 1",
            (place_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="店家不存在或已下架")
    return row_to_place(row)


@app.get("/api/categories")
def categories() -> dict[str, list[str]]:
    with db() as conn:
        category_rows = conn.execute(
            "SELECT my_category, my_categories FROM food_places WHERE is_public = 1"
        ).fetchall()
        cats = sorted(
            {
                category
                for row in category_rows
                for category in decode_category_values(row["my_categories"], row["my_category"])
            },
            key=lambda value: value.casefold(),
        )
        recs = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT recommend_level FROM food_places WHERE is_public = 1 AND recommend_level != '' ORDER BY recommend_level"
            ).fetchall()
        ]
    return {"categories": cats, "recommendLevels": recs}


@app.get("/api/search")
async def search_places(
    q: str = Query(..., min_length=1, max_length=80),
    city: str = Query("", max_length=40),
) -> dict[str, Any]:
    if not AMAP_WEB_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="AMAP_WEB_SERVICE_KEY is not configured")

    keyword, normalized_city = normalize_search(q, city)
    attempts = [
        {"types": "", "citylimit": "true" if normalized_city else "false"},
        {"types": "050000", "citylimit": "true" if normalized_city else "false"},
    ]
    if normalized_city:
        attempts.append({"types": "", "citylimit": "false"})
    raw_pois: list[dict[str, Any]] = []
    seen_pois: set[tuple[str, str, str]] = set()
    successful_request = False
    async with httpx.AsyncClient(timeout=8) as client:
        for attempt in attempts:
            params = {
                "key": AMAP_WEB_SERVICE_KEY,
                "keywords": keyword,
                "city": normalized_city,
                "citylimit": attempt["citylimit"],
                "types": attempt["types"],
                "extensions": "all",
                "offset": "20",
                "page": "1",
                "output": "json",
            }
            resp = await client.get("https://restapi.amap.com/v3/place/text", params=params)
            if resp.status_code != 200:
                continue
            candidate_data = resp.json()
            if candidate_data.get("status") != "1":
                continue
            successful_request = True
            candidate_pois = candidate_data.get("pois") if isinstance(candidate_data.get("pois"), list) else []
            for poi in candidate_pois:
                if not isinstance(poi, dict):
                    continue
                key = (
                    _string_value(poi.get("id")),
                    _string_value(poi.get("name")),
                    _string_value(poi.get("location")),
                )
                if key in seen_pois:
                    continue
                seen_pois.add(key)
                raw_pois.append(poi)
            if _has_strong_amap_match(candidate_pois, keyword):
                break
    if not successful_request:
        raise HTTPException(status_code=502, detail="Amap search failed")

    raw_pois = [
        poi
        for _, poi in sorted(
            enumerate(raw_pois),
            key=lambda item: (_amap_poi_search_score(item[1], keyword, normalized_city), -item[0]),
            reverse=True,
        )
    ][:20]
    pois = []
    for poi in raw_pois:
        normalized = normalize_amap_poi(poi)
        if normalized:
            pois.append(normalized)
    return {
        "items": pois,
        "query": {
            "keyword": keyword,
            "city": normalized_city,
            "count": len(pois),
        },
    }


@app.get("/api/developer/search")
async def search_developer_places(
    request: Request,
    q: str = Query(..., min_length=1, max_length=80),
    city: str = Query("", max_length=40),
) -> dict[str, Any]:
    read_developer_account(request)
    return await search_places(q=q, city=city)


@app.get("/api/regeo")
async def reverse_geocode(
    lng: float = Query(...),
    lat: float = Query(...),
) -> dict[str, Any]:
    if not AMAP_WEB_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="AMAP_WEB_SERVICE_KEY is not configured")

    params = {
        "key": AMAP_WEB_SERVICE_KEY,
        "location": f"{lng},{lat}",
        "extensions": "all",
        "radius": "120",
        "roadlevel": "0",
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get("https://restapi.amap.com/v3/geocode/regeo", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Amap reverse geocode failed")
    data = resp.json()
    if data.get("status") != "1":
        raise HTTPException(
            status_code=502,
            detail=data.get("info") or "Amap reverse geocode returned an error",
        )

    regeocode = data.get("regeocode") if isinstance(data.get("regeocode"), dict) else {}
    address_component = regeocode.get("addressComponent") if isinstance(regeocode.get("addressComponent"), dict) else {}
    pois = []
    for poi in regeocode.get("pois", []) if isinstance(regeocode.get("pois"), list) else []:
        if not isinstance(poi, dict):
            continue
        item = normalize_amap_poi({
            **poi,
            "cityname": _string_value(address_component.get("city")) or _string_value(address_component.get("province")),
            "adname": _string_value(address_component.get("district")),
        })
        if item:
            pois.append(item)

    return {
        "address": _string_value(regeocode.get("formatted_address")),
        "city": _string_value(address_component.get("city")) or _string_value(address_component.get("province")),
        "district": _string_value(address_component.get("district")),
        "lng": lng,
        "lat": lat,
        "items": pois,
    }


@app.get("/api/developer/regeo")
async def reverse_geocode_for_developer(
    request: Request,
    lng: float = Query(...),
    lat: float = Query(...),
) -> dict[str, Any]:
    read_developer_account(request)
    return await reverse_geocode(lng=lng, lat=lat)


@app.get("/api/poi-detail")
async def poi_detail(
    id: str = Query(..., min_length=1, max_length=80),
) -> dict[str, Any]:
    if not AMAP_WEB_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="AMAP_WEB_SERVICE_KEY is not configured")

    params = {
        "key": AMAP_WEB_SERVICE_KEY,
        "id": id,
        "extensions": "all",
        "output": "json",
    }
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get("https://restapi.amap.com/v3/place/detail", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Amap detail failed")
    data = resp.json()
    if data.get("status") != "1":
        raise HTTPException(
            status_code=502,
            detail=data.get("info") or "Amap detail returned an error",
        )

    pois = data.get("pois") if isinstance(data.get("pois"), list) else []
    if not pois:
        raise HTTPException(status_code=404, detail="Amap POI detail not found")
    normalized = normalize_amap_poi(pois[0])
    if not normalized:
        raise HTTPException(status_code=404, detail="Amap POI detail has no location")
    return {"item": normalized}


@app.get("/api/developer/poi-detail")
async def developer_poi_detail(
    request: Request,
    id: str = Query(..., min_length=1, max_length=80),
) -> dict[str, Any]:
    read_developer_account(request)
    return await poi_detail(id=id)


@app.get("/api/admin/places", response_model=list[Place])
def list_admin_places() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM food_places ORDER BY updated_at DESC"
        ).fetchall()
    return [row_to_place(row) for row in rows]


@app.get("/api/admin/places/{place_id}", response_model=Place)
def get_admin_place(place_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM food_places WHERE id = ?", (place_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Place not found")
    return row_to_place(row)


def validate_developer_username(username: str) -> str:
    normalized = username.strip().lower()
    if not re.fullmatch(r"admin[a-z0-9]{2,32}", normalized):
        raise HTTPException(
            status_code=400,
            detail="账号必须以 admin 开头，后面使用 2-32 位小写字母或数字",
        )
    return normalized


def account_with_place_count(conn: sqlite3.Connection, account_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT a.*,
               (
                   SELECT COUNT(*)
                   FROM food_places p
                   WHERE lower(trim(COALESCE(NULLIF(p.rating_author, ''), '吕俊泽')))
                         = lower(trim(a.author_name))
               ) AS place_count
        FROM developer_accounts a
        WHERE a.id = ?
        """,
        (account_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="作者账号不存在")
    result = public_account(row)
    result["place_count"] = row["place_count"]
    return result


@app.get("/api/admin/authors")
def list_admin_authors() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT a.*,
                   (
                       SELECT COUNT(*)
                       FROM food_places p
                       WHERE lower(trim(COALESCE(NULLIF(p.rating_author, ''), '吕俊泽')))
                             = lower(trim(a.author_name))
                   ) AS place_count
            FROM developer_accounts a
            ORDER BY a.id
            """
        ).fetchall()
    result = []
    for row in rows:
        item = public_account(row)
        item["place_count"] = row["place_count"]
        result.append(item)
    return result


@app.post("/api/admin/authors")
def create_admin_author(payload: DeveloperAccountIn) -> dict[str, Any]:
    username = validate_developer_username(payload.username)
    author_name = payload.author_name.strip()
    salt, digest = password_hash(INITIAL_DEVELOPER_PASSWORD)
    now = utc_now()
    try:
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO developer_accounts (
                    username, author_name, password_salt, password_hash,
                    must_change_password, is_active, last_login_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 1, ?, '', ?, ?)
                """,
                (username, author_name, salt, digest, 1 if payload.is_active else 0, now, now),
            )
            return account_with_place_count(conn, cur.lastrowid)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="账号或作者名已存在") from None


@app.put("/api/admin/authors/{account_id}")
def update_admin_author(
    account_id: int,
    payload: DeveloperAccountUpdate,
) -> dict[str, Any]:
    username = validate_developer_username(payload.username)
    author_name = payload.author_name.strip()
    now = utc_now()
    try:
        with db() as conn:
            existing = conn.execute(
                "SELECT * FROM developer_accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="作者账号不存在")
            conn.execute(
                """
                UPDATE developer_accounts
                SET username = ?, author_name = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (username, author_name, 1 if payload.is_active else 0, now, account_id),
            )
            if existing["author_name"] != author_name:
                conn.execute(
                    """
                    UPDATE food_places
                    SET rating_author = ?, updated_at = ?
                    WHERE lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽')))
                          = lower(trim(?))
                    """,
                    (author_name, now, existing["author_name"]),
                )
            if not payload.is_active:
                conn.execute(
                    "DELETE FROM developer_sessions WHERE account_id = ?",
                    (account_id,),
                )
            return account_with_place_count(conn, account_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="账号或作者名已存在") from None


@app.post("/api/admin/authors/{account_id}/reset-password")
def reset_admin_author_password(account_id: int) -> dict[str, Any]:
    salt, digest = password_hash(INITIAL_DEVELOPER_PASSWORD)
    now = utc_now()
    with db() as conn:
        result = conn.execute(
            """
            UPDATE developer_accounts
            SET password_salt = ?, password_hash = ?, must_change_password = 1, updated_at = ?
            WHERE id = ?
            """,
            (salt, digest, now, account_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="作者账号不存在")
        conn.execute(
            "DELETE FROM developer_sessions WHERE account_id = ?",
            (account_id,),
        )
        return account_with_place_count(conn, account_id)


@app.post("/api/admin/places", response_model=Place)
def create_place(payload: PlaceIn) -> dict[str, Any]:
    now = utc_now()
    category_values = payload_category_values(payload)
    primary_category = category_values[0] if category_values else ""
    encoded_categories = encode_category_values(category_values)
    with db() as conn:
        duplicate = find_duplicate_place(conn, payload)
        if duplicate:
            raise duplicate_place_error(duplicate)
        cur = conn.execute(
            """
            INSERT INTO food_places (
                map_provider, country_code, coordinate_system,
                provider_poi_id, name, address, lng, lat, city, district,
                provider_category, phone, business_hours, amap_detail_url,
                provider_detail_url,
                my_category, my_categories, rating, rating_author, recommend_level, review_url,
                review_text, tags, note, visited_at,
                cover_image, image_urls, hide_images, is_public, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.map_provider,
                payload.country_code,
                payload.coordinate_system,
                payload.provider_poi_id,
                payload.name,
                payload.address,
                payload.lng,
                payload.lat,
                payload.city,
                payload.district,
                payload.provider_category,
                payload.phone,
                payload.business_hours,
                payload.amap_detail_url,
                payload.provider_detail_url,
                primary_category,
                encoded_categories,
                payload.rating,
                payload.rating_author,
                payload.recommend_level,
                payload.review_url,
                payload.review_text,
                payload.tags,
                payload.note,
                payload.visited_at,
                payload.cover_image,
                payload.image_urls,
                1 if payload.hide_images else 0,
                1 if payload.is_public else 0,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM food_places WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return row_to_place(row)


@app.put("/api/admin/places/{place_id}", response_model=Place)
def update_place(place_id: int, payload: PlaceIn) -> dict[str, Any]:
    now = utc_now()
    category_values = payload_category_values(payload)
    primary_category = category_values[0] if category_values else ""
    encoded_categories = encode_category_values(category_values)
    with db() as conn:
        duplicate = find_duplicate_place(conn, payload, exclude_id=place_id)
        if duplicate:
            raise duplicate_place_error(duplicate)
        result = conn.execute(
            """
            UPDATE food_places SET
                map_provider = ?, country_code = ?, coordinate_system = ?,
                provider_poi_id = ?, name = ?, address = ?, lng = ?, lat = ?,
                city = ?, district = ?, provider_category = ?, phone = ?,
                business_hours = ?, amap_detail_url = ?, provider_detail_url = ?,
                my_category = ?, my_categories = ?,
                rating = ?, rating_author = ?, recommend_level = ?, review_url = ?,
                review_text = ?, tags = ?, note = ?, visited_at = ?,
                cover_image = ?, image_urls = ?, hide_images = ?,
                is_public = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.map_provider,
                payload.country_code,
                payload.coordinate_system,
                payload.provider_poi_id,
                payload.name,
                payload.address,
                payload.lng,
                payload.lat,
                payload.city,
                payload.district,
                payload.provider_category,
                payload.phone,
                payload.business_hours,
                payload.amap_detail_url,
                payload.provider_detail_url,
                primary_category,
                encoded_categories,
                payload.rating,
                payload.rating_author,
                payload.recommend_level,
                payload.review_url,
                payload.review_text,
                payload.tags,
                payload.note,
                payload.visited_at,
                payload.cover_image,
                payload.image_urls,
                1 if payload.hide_images else 0,
                1 if payload.is_public else 0,
                now,
                place_id,
            ),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Place not found")
        row = conn.execute("SELECT * FROM food_places WHERE id = ?", (place_id,)).fetchone()
    return row_to_place(row)


@app.delete("/api/admin/places/{place_id}")
def delete_place(place_id: int) -> dict[str, bool]:
    with db() as conn:
        result = conn.execute("DELETE FROM food_places WHERE id = ?", (place_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Place not found")
    return {"ok": True}
