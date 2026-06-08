import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            DELETE FROM food_places
            WHERE provider_poi_id != ''
              AND id NOT IN (
                SELECT MAX(id)
                FROM food_places
                WHERE provider_poi_id != ''
                GROUP BY map_provider, provider_poi_id
              )
            """
        )
        conn.execute(
            """
            DELETE FROM food_places
            WHERE provider_poi_id = ''
              AND name != ''
              AND address != ''
              AND id NOT IN (
                SELECT MAX(id)
                FROM food_places
                WHERE provider_poi_id = '' AND name != '' AND address != ''
                GROUP BY lower(trim(name)), lower(trim(address)), round(lng, 6), round(lat, 6)
              )
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def row_to_place(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["is_public"] = bool(item["is_public"])
    item["hide_images"] = bool(item.get("hide_images", 0))
    item["rating_author"] = item.get("rating_author") or "吕俊泽"
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
    if provider_poi_id:
        row = conn.execute(
            f"SELECT * FROM food_places WHERE map_provider = ? AND provider_poi_id = ?{exclude_sql} LIMIT 1",
            [map_provider, provider_poi_id, *exclude_params],
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
              {exclude_sql}
            LIMIT 1
            """,
            [name, address, payload.lng, payload.lat, *exclude_params],
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


@app.get("/")
def public_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/admin/")
def admin_page() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/admin")
def admin_page_no_slash() -> FileResponse:
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


@app.get("/api/places", response_model=list[Place])
def list_public_places(
    category: str = "",
    recommend: str = "",
) -> list[dict[str, Any]]:
    clauses = ["is_public = 1"]
    params: list[Any] = []
    if category:
        clauses.append("my_category = ?")
        params.append(category)
    if recommend:
        clauses.append("recommend_level = ?")
        params.append(recommend)
    sql = "SELECT * FROM food_places WHERE " + " AND ".join(clauses)
    sql += " ORDER BY COALESCE(rating, 0) DESC, updated_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_place(row) for row in rows]


@app.get("/api/places/{place_id}", response_model=Place)
def get_public_place(place_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM food_places WHERE id = ? AND is_public = 1",
            (place_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Place not found")
    return row_to_place(row)


@app.get("/api/categories")
def categories() -> dict[str, list[str]]:
    with db() as conn:
        cats = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT my_category FROM food_places WHERE is_public = 1 AND my_category != '' ORDER BY my_category"
            ).fetchall()
        ]
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
        {"types": "050000", "citylimit": "true" if normalized_city else "false"},
        {"types": "", "citylimit": "true" if normalized_city else "false"},
        {"types": "", "citylimit": "false"},
    ]
    data = None
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
            data = candidate_data
            if candidate_data.get("pois"):
                break
    if data is None:
        raise HTTPException(status_code=502, detail="Amap search failed")

    pois = []
    for poi in data.get("pois", []):
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


@app.post("/api/admin/places", response_model=Place)
def create_place(payload: PlaceIn) -> dict[str, Any]:
    now = utc_now()
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
                my_category, rating, rating_author, recommend_level, review_url,
                review_text, tags, note, visited_at,
                cover_image, image_urls, hide_images, is_public, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload.my_category,
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
                business_hours = ?, amap_detail_url = ?, provider_detail_url = ?, my_category = ?,
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
                payload.my_category,
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
