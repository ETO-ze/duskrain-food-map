import os
import re
import json
import base64
import html
import hashlib
import hmac
import secrets
import sqlite3
import smtplib
import ssl
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("FOOD_MAP_DATA_DIR", str(APP_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "food_map.db"
AVATAR_DIR = DATA_DIR / "avatars"

AMAP_WEB_SERVICE_KEY = os.getenv("AMAP_WEB_SERVICE_KEY", "").strip()
AMAP_JS_KEY = os.getenv("AMAP_JS_KEY", "").strip()
AMAP_SECURITY_CODE = os.getenv("AMAP_SECURITY_CODE", "").strip()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
DEVELOPER_SESSION_COOKIE = "duskrain_developer_session"
DEVELOPER_SESSION_HOURS = 24
INITIAL_DEVELOPER_PASSWORD = "123123"
PASSWORD_ITERATIONS = 310_000
PASSWORD_MIN_LENGTH = 8
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_FAILURES: dict[str, list[datetime]] = {}
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

PUBLIC_BASE_URL = os.getenv("FOOD_MAP_PUBLIC_BASE_URL", "https://duskrain.cn/food-map").rstrip("/")
DUSKRAIN_HOME_URL = os.getenv("DUSKRAIN_HOME_URL", "https://duskrain.cn/").strip()
SMTP_HOST = os.getenv("FOOD_MAP_SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("FOOD_MAP_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("FOOD_MAP_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = re.sub(r"\s+", "", os.getenv("FOOD_MAP_SMTP_PASSWORD", ""))
SMTP_FROM_EMAIL = os.getenv("FOOD_MAP_SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_FROM_NAME = os.getenv("FOOD_MAP_SMTP_FROM_NAME", "DuskRain").strip()
SMTP_USE_SSL = os.getenv("FOOD_MAP_SMTP_USE_SSL", "false").strip().lower() == "true"

GOOGLE_CLIENT_ID = os.getenv("FOOD_MAP_GOOGLE_CLIENT_ID", os.getenv("DUSKRAIN_AUTH_GOOGLE_CLIENT_ID", "")).strip()
GOOGLE_CLIENT_SECRET = os.getenv("FOOD_MAP_GOOGLE_CLIENT_SECRET", os.getenv("DUSKRAIN_AUTH_GOOGLE_CLIENT_SECRET", "")).strip()
GITHUB_CLIENT_ID = os.getenv("FOOD_MAP_GITHUB_CLIENT_ID", os.getenv("DUSKRAIN_AUTH_GITHUB_CLIENT_ID", "")).strip()
GITHUB_CLIENT_SECRET = os.getenv("FOOD_MAP_GITHUB_CLIENT_SECRET", os.getenv("DUSKRAIN_AUTH_GITHUB_CLIENT_SECRET", "")).strip()
GOOGLE_OAUTH_ENABLED = os.getenv("FOOD_MAP_GOOGLE_OAUTH_ENABLED", "false").strip().lower() == "true"
GITHUB_OAUTH_ENABLED = os.getenv("FOOD_MAP_GITHUB_OAUTH_ENABLED", "false").strip().lower() == "true"
PHONE_LOGIN_ENABLED = os.getenv("FOOD_MAP_PHONE_LOGIN_ENABLED", "false").strip().lower() == "true"
PHONE_IDENTITY_PROVIDER = "phone"
OAUTH_AVATAR_MAX_BYTES = 2 * 1024 * 1024
OAUTH_AVATAR_HOSTS = {
    "google": ("googleusercontent.com",),
    "github": ("avatars.githubusercontent.com",),
}

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


class PathPrefixMiddleware:
    """Accept the production /food-map prefix during direct local access."""

    def __init__(self, application: Any, prefix: str) -> None:
        self.application = application
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = scope.get("path", "")
        if scope.get("type") in {"http", "websocket"} and (
            path == self.prefix or path.startswith(f"{self.prefix}/")
        ):
            scope = dict(scope)
            stripped_path = path[len(self.prefix):] or "/"
            scope["path"] = stripped_path
            scope["raw_path"] = stripped_path.encode("utf-8")
        await self.application(scope, receive, send)


app = FastAPI(title="DuskRain Food Map")
app.add_middleware(PathPrefixMiddleware, prefix="/food-map")
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=APP_DIR / "static", check_dir=False), name="static")
app.mount("/media/avatars", StaticFiles(directory=AVATAR_DIR), name="developer-avatars")


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
    login: str = Field(..., min_length=3, max_length=254)
    # Legacy accounts may still have the old six-character bootstrap password.
    # Every newly created or changed password is validated at eight characters.
    password: str = Field(..., min_length=6, max_length=128)


class DeveloperPasswordChange(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class DeveloperInvitationIn(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., min_length=3, max_length=254)


class DeveloperAccountUpdate(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(default="", max_length=254)
    is_active: bool = True


class DeveloperAccountDelete(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=80)


class DeveloperActivationToken(BaseModel):
    token: str = Field(..., min_length=32, max_length=256)


class DeveloperActivationComplete(DeveloperActivationToken):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class DeveloperProfileUpdate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)


class DeveloperPasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class DeveloperPasswordResetComplete(DeveloperActivationToken):
    password: str = Field(..., min_length=8, max_length=128)


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


def modern_password_hash(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def account_password_matches(account: sqlite3.Row, password: str) -> bool:
    algorithm = row_value(account, "password_algorithm", "pbkdf2_sha256")
    digest = row_value(account, "password_hash", "")
    if not digest:
        return False
    if algorithm == "argon2id":
        try:
            return PASSWORD_HASHER.verify(digest, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    salt = row_value(account, "password_salt", "")
    if not salt:
        return False
    try:
        return password_matches(password, salt, digest)
    except ValueError:
        return False


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def row_value(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    return row[key] if key in row.keys() else default


def normalize_email(email: str, required: bool = False) -> str:
    normalized = email.strip().casefold()
    if not normalized and not required:
        return ""
    if (
        not normalized
        or len(normalized) > 254
        or normalized.count("@") != 1
        or normalized.startswith("@")
        or normalized.endswith("@")
        or "." not in normalized.rsplit("@", 1)[1]
    ):
        raise HTTPException(status_code=400, detail="请输入有效邮箱")
    return normalized


RESERVED_USERNAMES = {
    "admin", "administrator", "api", "auth", "developer", "duskrain", "foodmap",
    "help", "login", "logout", "root", "security", "support", "system",
}


def validate_developer_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])?", normalized):
        raise HTTPException(
            status_code=400,
            detail="账号名需为 3-32 位英文字母、数字、点、下划线或连字符，并以字母或数字开头和结尾",
        )
    if normalized in RESERVED_USERNAMES or normalized.startswith("invite_"):
        raise HTTPException(status_code=400, detail="该账号名不可使用")
    return normalized


def validate_new_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"密码至少需要 {PASSWORD_MIN_LENGTH} 位")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="密码不能超过 128 位")
    if password == INITIAL_DEVELOPER_PASSWORD:
        raise HTTPException(status_code=400, detail="不能使用旧的共享初始密码")


def account_bound_providers(conn: sqlite3.Connection, account_id: int) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT provider, provider_login, provider_email, created_at
        FROM developer_identities
        WHERE account_id = ?
        ORDER BY provider
        """,
        (account_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def public_account(row: sqlite3.Row, conn: Optional[sqlite3.Connection] = None) -> dict[str, Any]:
    status = row_value(row, "account_status", "active")
    username = row["username"]
    if status == "pending_invite" and username.startswith("invite_"):
        username = ""
    result = {
        "id": row["id"],
        "username": username,
        "author_name": row["author_name"],
        "email": row_value(row, "email", ""),
        "email_verified": bool(row_value(row, "email_verified_at", "")),
        "account_status": status,
        "avatar_url": (
            f"/food-map/media/avatars/{row_value(row, 'avatar_filename', '')}"
            if row_value(row, "avatar_filename", "") else ""
        ),
        "is_active": bool(row["is_active"]),
        "must_change_password": bool(row["must_change_password"]),
        "last_login_at": row["last_login_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if conn is not None:
        result["bound_providers"] = account_bound_providers(conn, row["id"])
    return result


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM_EMAIL)


def send_account_email(recipient: str, subject: str, text_body: str, html_body: str) -> None:
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="邮件服务尚未配置")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    try:
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=context) as client:
                client.login(SMTP_USERNAME, SMTP_PASSWORD)
                client.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as client:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
                client.login(SMTP_USERNAME, SMTP_PASSWORD)
                client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=502, detail="邮件发送失败，请稍后重试") from exc


def create_session(
    conn: sqlite3.Connection,
    account_id: int,
    request: Request,
    login_method: str,
) -> tuple[str, str]:
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=DEVELOPER_SESSION_HOURS)).isoformat()
    token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO developer_sessions (
            account_id, token_hash, expires_at, created_at, last_seen_at,
            login_method, ip_address, user_agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            session_token_hash(token),
            expires_at,
            now,
            now,
            login_method,
            request.client.host if request.client else "",
            request.headers.get("user-agent", "")[:300],
        ),
    )
    conn.execute(
        "UPDATE developer_accounts SET last_login_at = ?, updated_at = ? WHERE id = ?",
        (now, now, account_id),
    )
    return token, expires_at


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        DEVELOPER_SESSION_COOKIE,
        token,
        max_age=DEVELOPER_SESSION_HOURS * 60 * 60,
        path="/food-map",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def create_one_time_token(
    conn: sqlite3.Connection,
    table: str,
    account_id: int,
    lifetime: timedelta,
) -> str:
    if table not in {"developer_invitations", "developer_password_resets"}:
        raise ValueError("Unsupported token table")
    token = secrets.token_urlsafe(40)
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + lifetime).isoformat()
    conn.execute(
        f"UPDATE {table} SET used_at = ? WHERE account_id = ? AND used_at = ''",
        (now, account_id),
    )
    conn.execute(
        f"""
        INSERT INTO {table} (account_id, token_hash, expires_at, used_at, created_at, sent_at)
        VALUES (?, ?, ?, '', ?, '')
        """,
        (account_id, session_token_hash(token), expires_at, now),
    )
    return token


def branded_account_email_html(
    *,
    title: str,
    preheader: str,
    greeting: str,
    paragraphs: list[str],
    cta_label: str,
    cta_url: str,
    validity_note: str,
) -> str:
    safe_title = html.escape(title)
    safe_preheader = html.escape(preheader)
    safe_greeting = html.escape(greeting)
    safe_cta_label = html.escape(cta_label)
    safe_cta_url = html.escape(cta_url, quote=True)
    safe_validity_note = html.escape(validity_note)
    paragraph_html = "".join(
        f'<p style="margin:0 0 16px;color:#42566f;font-size:15px;line-height:1.75;">{html.escape(value)}</p>'
        for value in paragraphs
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f2f5f9;font-family:Inter,'Noto Sans SC','Segoe UI',Arial,sans-serif;color:#142238;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{safe_preheader}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;background:#f2f5f9;">
    <tr><td align="center" style="padding:36px 16px;">
      <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid #cbd5e1;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:24px 30px;background:#142238;">
          <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
            <td style="padding-right:12px;"><img src="https://duskrain.cn/black-hole/assets/logo.webp" width="42" height="42" alt="DuskRain" style="display:block;width:42px;height:42px;border:0;border-radius:10px;"></td>
            <td><div style="color:#ffffff;font-size:19px;font-weight:800;letter-spacing:-0.02em;">DuskRain</div><div style="margin-top:3px;color:#9fc7d2;font-size:11px;letter-spacing:0.14em;">AUTHOR WORKSPACE</div></td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:38px 38px 34px;">
          <div style="margin:0 0 10px;color:#007a9d;font-size:12px;font-weight:800;letter-spacing:0.13em;">DUSKRAIN ACCOUNT</div>
          <h1 style="margin:0 0 24px;color:#142238;font-size:26px;line-height:1.35;letter-spacing:-0.03em;">{safe_title}</h1>
          <p style="margin:0 0 16px;color:#142238;font-size:17px;font-weight:700;line-height:1.6;">{safe_greeting}</p>
          {paragraph_html}
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px 0 24px;"><tr><td bgcolor="#007a9d" style="border-radius:9px;">
            <a href="{safe_cta_url}" style="display:inline-block;padding:13px 24px;color:#ffffff;text-decoration:none;font-size:15px;font-weight:800;line-height:20px;">{safe_cta_label}</a>
          </td></tr></table>
          <div style="padding:14px 16px;border-left:3px solid #7bbdca;background:#f2f8fa;color:#536a7f;font-size:13px;line-height:1.65;">{safe_validity_note}</div>
          <p style="margin:22px 0 7px;color:#74869a;font-size:12px;line-height:1.6;">如果按钮无法打开，请复制以下地址到浏览器：</p>
          <p style="margin:0;color:#52677e;font-size:12px;line-height:1.6;word-break:break-all;"><a href="{safe_cta_url}" style="color:#007a9d;text-decoration:underline;">{safe_cta_url}</a></p>
        </td></tr>
        <tr><td style="padding:22px 30px;border-top:1px solid #d8e1ea;background:#f8fafc;text-align:center;">
          <p style="margin:0 0 12px;color:#617389;font-size:12px;line-height:1.65;">此邮件由 DuskRain 系统自动发送，请勿直接回复。若你没有发起或预期此操作，可以安全地忽略本邮件。</p>
          <p style="margin:0 0 12px;font-size:12px;line-height:1.7;"><a href="https://duskrain.cn/#about" style="color:#425d73;text-decoration:none;">关于 DuskRain</a><span style="padding:0 9px;color:#a3afbd;">·</span><a href="https://duskrain.cn/privacy/" style="color:#425d73;text-decoration:none;">隐私政策</a><span style="padding:0 9px;color:#a3afbd;">·</span><a href="https://duskrain.cn/terms/" style="color:#425d73;text-decoration:none;">服务条款</a></p>
          <p style="margin:0;color:#8a98a8;font-size:11px;">Copyright © 2026 ETO-ze. All rights reserved.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_activation_email(account: sqlite3.Row, token: str) -> None:
    link = f"{PUBLIC_BASE_URL}/developer/?activate={token}"
    author_name = account["author_name"]
    stored_username = str(row_value(account, "username", "")).strip()
    existing_username = stored_username if stored_username and not stored_username.startswith("invite_") else ""
    subject = "验证邮箱并激活 DuskRain 作者账户"
    username_text = f"系统已为你保留原账号名：{existing_username}。\n\n" if existing_username else ""
    text = (
        f"{author_name}，你好。\n\n"
        "你收到这封邮件，是因为 DuskRain 超级管理员邀请你成为吕其林美食指南的作者。"
        "完成邮箱验证后，你可以设置自己的账号名和密码，并在作者工作台维护本人名下的店家、评价和资料。\n\n"
        f"{username_text}"
        "请在 24 小时内打开下面的链接验证邮箱并激活账户：\n\n"
        f"{link}\n\n"
        "该链接只能使用一次。若你没有预期收到此邀请，可以忽略本邮件。\n\n"
        "关于 DuskRain：https://duskrain.cn/#about\n"
        "隐私政策：https://duskrain.cn/privacy/\n"
        "服务条款：https://duskrain.cn/terms/"
    )
    paragraphs = [
        "你收到这封邮件，是因为 DuskRain 超级管理员邀请你成为吕其林美食指南的作者。",
        "完成邮箱验证后，你可以设置自己的账号名和密码，并在作者工作台维护本人名下的店家、评价和资料。",
    ]
    if existing_username:
        paragraphs.append(f"系统已为你保留原账号名：{existing_username}。激活页面会自动填写，之后仍可在账号与安全中修改。")
    html_body = branded_account_email_html(
        title="验证邮箱并激活作者账户",
        preheader="完成邮箱验证，设置你的 DuskRain 作者工作台账号。",
        greeting=f"{author_name}，你好。",
        paragraphs=paragraphs,
        cta_label="验证邮箱并激活账户",
        cta_url=link,
        validity_note="为了保护账户安全，此链接将在 24 小时后失效，且只能使用一次。请勿将本邮件或链接转发给他人。",
    )
    send_account_email(account["email"], subject, text, html_body)


def send_password_reset_email(account: sqlite3.Row, token: str) -> None:
    link = f"{PUBLIC_BASE_URL}/developer/?reset={token}"
    subject = "重置 DuskRain 作者工作台密码"
    text = (
        f"{account['author_name']}，你好。\n\n"
        f"请在 1 小时内打开以下链接重置 DuskRain 作者工作台密码：\n\n{link}\n\n"
        "该链接只能使用一次。如果不是你发起的请求，可以忽略本邮件。"
    )
    html_body = branded_account_email_html(
        title="重置作者工作台密码",
        preheader="使用一次性安全链接重置你的 DuskRain 作者工作台密码。",
        greeting=f"{account['author_name']}，你好。",
        paragraphs=[
            "我们收到了你的 DuskRain 作者工作台密码重置请求。",
            "点击下面的按钮设置新密码；完成后，其他设备上的工作台会话将退出。",
        ],
        cta_label="重置密码",
        cta_url=link,
        validity_note="为了保护账户安全，此链接将在 1 小时后失效，且只能使用一次。如果不是你发起的请求，无需进行任何操作。",
    )
    send_account_email(account["email"], subject, text, html_body)


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
            WHERE s.token_hash = ? AND s.expires_at > ?
              AND a.is_active = 1 AND a.account_status = 'active'
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
                owner_account_id INTEGER,
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
            "owner_account_id": "ALTER TABLE food_places ADD COLUMN owner_account_id INTEGER",
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
        account_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(developer_accounts)").fetchall()
        }
        account_migrations = {
            "email": "ALTER TABLE developer_accounts ADD COLUMN email TEXT NOT NULL DEFAULT ''",
            "email_verified_at": "ALTER TABLE developer_accounts ADD COLUMN email_verified_at TEXT NOT NULL DEFAULT ''",
            "account_status": "ALTER TABLE developer_accounts ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'",
            "avatar_filename": "ALTER TABLE developer_accounts ADD COLUMN avatar_filename TEXT NOT NULL DEFAULT ''",
            "password_algorithm": "ALTER TABLE developer_accounts ADD COLUMN password_algorithm TEXT NOT NULL DEFAULT 'pbkdf2_sha256'",
            "password_updated_at": "ALTER TABLE developer_accounts ADD COLUMN password_updated_at TEXT NOT NULL DEFAULT ''",
        }
        for column, sql in account_migrations.items():
            if column not in account_columns:
                conn.execute(sql)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_developer_accounts_email
            ON developer_accounts(lower(email))
            WHERE trim(email) != ''
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
        session_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(developer_sessions)").fetchall()
        }
        session_migrations = {
            "login_method": "ALTER TABLE developer_sessions ADD COLUMN login_method TEXT NOT NULL DEFAULT 'password'",
            "ip_address": "ALTER TABLE developer_sessions ADD COLUMN ip_address TEXT NOT NULL DEFAULT ''",
            "user_agent": "ALTER TABLE developer_sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT ''",
        }
        for column, sql in session_migrations.items():
            if column not in session_columns:
                conn.execute(sql)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_developer_sessions_account ON developer_sessions(account_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(account_id) REFERENCES developer_accounts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(account_id) REFERENCES developer_accounts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_subject TEXT NOT NULL,
                provider_login TEXT NOT NULL DEFAULT '',
                provider_email TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES developer_accounts(id) ON DELETE CASCADE,
                UNIQUE(provider, provider_subject),
                UNIQUE(account_id, provider)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS developer_oauth_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_hash TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                mode TEXT NOT NULL,
                account_id INTEGER,
                code_verifier TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES developer_accounts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_developer_invitations_account ON developer_invitations(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_developer_resets_account ON developer_password_resets(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_developer_identities_account ON developer_identities(account_id)")
        if os.getenv("FOOD_MAP_SEED_LEGACY_ACCOUNTS", "false").strip().lower() == "true":
            seed_developer_accounts(conn)
        conn.execute(
            """
            UPDATE food_places
            SET owner_account_id = (
                SELECT a.id FROM developer_accounts a
                WHERE lower(trim(a.author_name)) = lower(trim(food_places.rating_author))
                LIMIT 1
            )
            WHERE owner_account_id IS NULL
              AND EXISTS (
                SELECT 1 FROM developer_accounts a
                WHERE lower(trim(a.author_name)) = lower(trim(food_places.rating_author))
              )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_food_places_owner ON food_places(owner_account_id)")
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


@app.get("/guide")
@app.get("/guide/")
@app.get("/guide/2026")
@app.get("/guide/2026/")
@app.get("/guide/archive")
@app.get("/guide/archive/")
def lu_guide_page() -> FileResponse:
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
    login = payload.login.strip().casefold()
    client_ip = request.client.host if request.client else "unknown"
    attempt_key = f"{client_ip}:{login}"
    cutoff = datetime.now(timezone.utc) - LOGIN_FAILURE_WINDOW
    failures = [attempt for attempt in LOGIN_FAILURES.get(attempt_key, []) if attempt > cutoff]
    if len(failures) >= LOGIN_FAILURE_LIMIT:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后重试")
    with db() as conn:
        account = conn.execute(
            """
            SELECT * FROM developer_accounts
            WHERE lower(username) = ? OR (trim(email) != '' AND lower(email) = ?)
            LIMIT 1
            """,
            (login, login),
        ).fetchone()
        if (
            not account
            or not account["is_active"]
            or account["account_status"] != "active"
            or not account_password_matches(account, payload.password)
        ):
            failures.append(datetime.now(timezone.utc))
            LOGIN_FAILURES[attempt_key] = failures
            raise HTTPException(status_code=401, detail="账号或密码错误")
        LOGIN_FAILURES.pop(attempt_key, None)
        now = utc_now()
        if account["password_algorithm"] != "argon2id":
            conn.execute(
                """
                UPDATE developer_accounts
                SET password_salt = '', password_hash = ?, password_algorithm = 'argon2id',
                    password_updated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (modern_password_hash(payload.password), now, now, account["id"]),
            )
        token, _ = create_session(conn, account["id"], request, "password")
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?",
            (account["id"],),
        ).fetchone()
        result = public_account(account, conn)
    set_session_cookie(response, token)
    return result


@app.get("/api/developer/session")
def developer_session(request: Request) -> dict[str, Any]:
    account = read_developer_account(request, require_password_changed=False)
    with db() as conn:
        return public_account(account, conn)


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
    if not account_password_matches(account, payload.current_password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    validate_new_password(payload.new_password)
    digest = modern_password_hash(payload.new_password)
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE developer_accounts
            SET password_salt = '', password_hash = ?, password_algorithm = 'argon2id',
                password_updated_at = ?, must_change_password = 0, updated_at = ?
            WHERE id = ?
            """,
            (digest, now, now, account["id"]),
        )
        conn.execute(
            "DELETE FROM developer_sessions WHERE account_id = ? AND token_hash != ?",
            (
                account["id"],
                session_token_hash(request.cookies.get(DEVELOPER_SESSION_COOKIE, "")),
            ),
        )
        updated = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?",
            (account["id"],),
        ).fetchone()
        return public_account(updated, conn)


def read_valid_account_token(
    conn: sqlite3.Connection,
    table: str,
    token: str,
) -> sqlite3.Row:
    if table not in {"developer_invitations", "developer_password_resets"}:
        raise ValueError("Unsupported token table")
    row = conn.execute(
        f"""
        SELECT t.id AS token_id, t.expires_at, t.used_at, a.*
        FROM {table} t
        JOIN developer_accounts a ON a.id = t.account_id
        WHERE t.token_hash = ? AND t.used_at = '' AND t.expires_at > ?
        LIMIT 1
        """,
        (session_token_hash(token), utc_now()),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="链接无效或已过期")
    return row


@app.get("/api/developer/auth/config")
def developer_auth_config() -> dict[str, Any]:
    return {
        "password_min_length": PASSWORD_MIN_LENGTH,
        "home_url": DUSKRAIN_HOME_URL,
        "email_enabled": smtp_configured(),
        "oauth_providers": {
            "google": bool(GOOGLE_OAUTH_ENABLED and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "github": bool(GITHUB_OAUTH_ENABLED and GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET),
        },
        # Reserved capability for a future verified-SMS adapter. It stays hidden while disabled.
        "identity_capabilities": {PHONE_IDENTITY_PROVIDER: PHONE_LOGIN_ENABLED},
    }


@app.post("/api/developer/activation/inspect")
def inspect_developer_activation(payload: DeveloperActivationToken) -> dict[str, Any]:
    with db() as conn:
        row = read_valid_account_token(conn, "developer_invitations", payload.token)
        stored_username = row["username"].strip()
        existing_username = bool(stored_username and not stored_username.startswith("invite_"))
        return {
            "author_name": row["author_name"],
            "email": row["email"],
            "username": stored_username if existing_username else "",
            "existing_username": existing_username,
        }


@app.post("/api/developer/activation/complete")
def complete_developer_activation(
    payload: DeveloperActivationComplete,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    username = validate_developer_username(payload.username)
    validate_new_password(payload.password)
    now = utc_now()
    try:
        with db() as conn:
            row = read_valid_account_token(conn, "developer_invitations", payload.token)
            if not row["is_active"]:
                raise HTTPException(status_code=403, detail="账户已停用，请联系超级管理员")
            conn.execute(
                """
                UPDATE developer_accounts
                SET username = ?, password_salt = '', password_hash = ?,
                    password_algorithm = 'argon2id', password_updated_at = ?,
                    must_change_password = 0, account_status = 'active',
                    email_verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    username,
                    modern_password_hash(payload.password),
                    now,
                    now,
                    now,
                    row["id"],
                ),
            )
            conn.execute(
                "UPDATE developer_invitations SET used_at = ? WHERE id = ?",
                (now, row["token_id"]),
            )
            conn.execute("DELETE FROM developer_sessions WHERE account_id = ?", (row["id"],))
            token, _ = create_session(conn, row["id"], request, "activation")
            account = conn.execute(
                "SELECT * FROM developer_accounts WHERE id = ?", (row["id"],)
            ).fetchone()
            result = public_account(account, conn)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该账号名已被使用") from None
    set_session_cookie(response, token)
    return result


@app.post("/api/developer/password/forgot")
def request_developer_password_reset(payload: DeveloperPasswordResetRequest) -> dict[str, bool]:
    email = normalize_email(payload.email, required=True)
    if not smtp_configured():
        return {"ok": True}
    with db() as conn:
        account = conn.execute(
            """
            SELECT * FROM developer_accounts
            WHERE lower(email) = ? AND trim(email_verified_at) != ''
              AND is_active = 1 AND account_status = 'active'
            LIMIT 1
            """,
            (email,),
        ).fetchone()
        if not account:
            return {"ok": True}
        token = create_one_time_token(conn, "developer_password_resets", account["id"], timedelta(hours=1))
    send_password_reset_email(account, token)
    with db() as conn:
        conn.execute(
            "UPDATE developer_password_resets SET sent_at = ? WHERE token_hash = ?",
            (utc_now(), session_token_hash(token)),
        )
    return {"ok": True}


@app.post("/api/developer/password/reset")
def complete_developer_password_reset(payload: DeveloperPasswordResetComplete) -> dict[str, bool]:
    validate_new_password(payload.password)
    now = utc_now()
    with db() as conn:
        row = read_valid_account_token(conn, "developer_password_resets", payload.token)
        if not row["is_active"] or row["account_status"] != "active":
            raise HTTPException(status_code=403, detail="账户不可用，请联系超级管理员")
        conn.execute(
            """
            UPDATE developer_accounts
            SET password_salt = '', password_hash = ?, password_algorithm = 'argon2id',
                password_updated_at = ?, must_change_password = 0,
                email_verified_at = CASE WHEN email_verified_at = '' THEN ? ELSE email_verified_at END,
                updated_at = ?
            WHERE id = ?
            """,
            (modern_password_hash(payload.password), now, now, now, row["id"]),
        )
        conn.execute(
            "UPDATE developer_password_resets SET used_at = ? WHERE id = ?",
            (now, row["token_id"]),
        )
        conn.execute("DELETE FROM developer_sessions WHERE account_id = ?", (row["id"],))
    return {"ok": True}


@app.put("/api/developer/profile")
def update_developer_profile(
    payload: DeveloperProfileUpdate,
    request: Request,
) -> dict[str, Any]:
    account = read_developer_account(request)
    username = validate_developer_username(payload.username)
    now = utc_now()
    try:
        with db() as conn:
            conn.execute(
                "UPDATE developer_accounts SET username = ?, updated_at = ? WHERE id = ?",
                (username, now, account["id"]),
            )
            updated = conn.execute(
                "SELECT * FROM developer_accounts WHERE id = ?", (account["id"],)
            ).fetchone()
            return public_account(updated, conn)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该账号名已被使用") from None


def avatar_image_from_bytes(content: bytes) -> Image.Image:
    if not content or len(content) > OAUTH_AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="头像文件需小于 2 MB")
    try:
        image = Image.open(BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="仅支持 JPEG、PNG 或 WebP 图片") from None
    if (image.format or "").upper() not in {"JPEG", "PNG", "WEBP"}:
        raise HTTPException(status_code=400, detail="仅支持 JPEG、PNG 或 WebP 图片")
    if image.width * image.height > 25_000_000:
        raise HTTPException(status_code=400, detail="头像图片尺寸过大")
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    return image


def oauth_avatar_url_allowed(provider: str, avatar_url: str) -> bool:
    try:
        parsed = urlparse(avatar_url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in OAUTH_AVATAR_HOSTS.get(provider, ())
    )


def download_oauth_avatar(provider: str, avatar_url: str) -> bytes:
    if not oauth_avatar_url_allowed(provider, avatar_url):
        return b""
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            with client.stream("GET", avatar_url, headers={"Accept": "image/avif,image/webp,image/png,image/jpeg"}) as response:
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length > OAUTH_AVATAR_MAX_BYTES:
                    return b""
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > OAUTH_AVATAR_MAX_BYTES:
                        return b""
                    chunks.append(chunk)
                return b"".join(chunks)
    except (httpx.HTTPError, ValueError):
        return b""


def maybe_import_oauth_avatar(account_id: int, provider: str, avatar_url: str) -> bool:
    """Import a trusted provider avatar only when the author has no local avatar."""
    if not avatar_url:
        return False
    with db() as conn:
        account = conn.execute(
            "SELECT avatar_filename FROM developer_accounts WHERE id = ?", (account_id,)
        ).fetchone()
    if not account or row_value(account, "avatar_filename", ""):
        return False
    content = download_oauth_avatar(provider, avatar_url)
    if not content:
        return False
    try:
        image = avatar_image_from_bytes(content)
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"account-{account_id}-{secrets.token_hex(10)}.webp"
        target = AVATAR_DIR / filename
        image.save(target, format="WEBP", quality=88, method=6)
        with db() as conn:
            cursor = conn.execute(
                """
                UPDATE developer_accounts
                SET avatar_filename = ?, updated_at = ?
                WHERE id = ? AND avatar_filename = ''
                """,
                (filename, utc_now(), account_id),
            )
        if cursor.rowcount != 1:
            target.unlink(missing_ok=True)
            return False
        return True
    except (HTTPException, OSError, sqlite3.Error):
        if "target" in locals():
            target.unlink(missing_ok=True)
        return False


@app.post("/api/developer/avatar")
def upload_developer_avatar(
    request: Request,
    avatar: UploadFile = File(...),
) -> dict[str, Any]:
    account = read_developer_account(request)
    content = avatar.file.read(OAUTH_AVATAR_MAX_BYTES + 1)
    image = avatar_image_from_bytes(content)
    filename = f"account-{account['id']}-{secrets.token_hex(10)}.webp"
    target = AVATAR_DIR / filename
    image.save(target, format="WEBP", quality=88, method=6)
    old_filename = row_value(account, "avatar_filename", "")
    with db() as conn:
        conn.execute(
            "UPDATE developer_accounts SET avatar_filename = ?, updated_at = ? WHERE id = ?",
            (filename, utc_now(), account["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?", (account["id"],)
        ).fetchone()
        result = public_account(updated, conn)
    if old_filename:
        old_path = AVATAR_DIR / Path(old_filename).name
        if old_path != target:
            old_path.unlink(missing_ok=True)
    return result


@app.delete("/api/developer/avatar")
def delete_developer_avatar(request: Request) -> dict[str, Any]:
    account = read_developer_account(request)
    old_filename = row_value(account, "avatar_filename", "")
    with db() as conn:
        conn.execute(
            "UPDATE developer_accounts SET avatar_filename = '', updated_at = ? WHERE id = ?",
            (utc_now(), account["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?", (account["id"],)
        ).fetchone()
        result = public_account(updated, conn)
    if old_filename:
        (AVATAR_DIR / Path(old_filename).name).unlink(missing_ok=True)
    return result


def oauth_credentials(provider: str) -> tuple[str, str]:
    if provider == "google":
        if not GOOGLE_OAUTH_ENABLED:
            raise HTTPException(status_code=503, detail="Google 登录尚未启用")
        values = (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
    elif provider == "github":
        if not GITHUB_OAUTH_ENABLED:
            raise HTTPException(status_code=503, detail="GitHub 登录尚未启用")
        values = (GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
    else:
        raise HTTPException(status_code=404, detail="不支持该登录方式")
    if not all(values):
        raise HTTPException(status_code=503, detail="该登录方式尚未配置")
    return values


def oauth_redirect_uri(provider: str) -> str:
    return f"{PUBLIC_BASE_URL}/api/developer/oauth/{provider}/callback"


def oauth_result_redirect(result: str) -> RedirectResponse:
    return RedirectResponse(f"{PUBLIC_BASE_URL}/developer/?oauth_result={result}", status_code=303)


def oauth_provider_identity(provider: str, code: str, verifier: str) -> dict[str, str]:
    client_id, client_secret = oauth_credentials(provider)
    redirect_uri = oauth_redirect_uri(provider)
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            if provider == "google":
                token_response = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "code_verifier": verifier,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                )
                token_response.raise_for_status()
                access_token = token_response.json().get("access_token", "")
                user_response = client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                user_response.raise_for_status()
                user = user_response.json()
                return {
                    "subject": str(user.get("sub", "")),
                    "login": str(user.get("name", ""))[:120],
                    "email": str(user.get("email", "")).casefold()[:254],
                    "avatar_url": str(user.get("picture", ""))[:1000],
                }
            token_response = client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token", "")
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
            }
            user_response = client.get("https://api.github.com/user", headers=headers)
            user_response.raise_for_status()
            user = user_response.json()
            email = str(user.get("email") or "").casefold()
            if not email:
                email_response = client.get("https://api.github.com/user/emails", headers=headers)
                email_response.raise_for_status()
                emails = email_response.json()
                primary = next(
                    (item for item in emails if item.get("primary") and item.get("verified")),
                    next((item for item in emails if item.get("verified")), {}),
                )
                email = str(primary.get("email", "")).casefold()
            return {
                "subject": str(user.get("id", "")),
                "login": str(user.get("login", ""))[:120],
                "email": email[:254],
                "avatar_url": str(user.get("avatar_url", ""))[:1000],
            }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="第三方身份验证失败") from exc


@app.get("/api/developer/oauth/{provider}/start")
def start_developer_oauth(
    provider: str,
    request: Request,
    mode: str = Query(default="login", pattern="^(login|bind)$"),
) -> RedirectResponse:
    client_id, _ = oauth_credentials(provider)
    account_id: Optional[int] = None
    if mode == "bind":
        account_id = read_developer_account(request)["id"]
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    with db() as conn:
        conn.execute("DELETE FROM developer_oauth_states WHERE expires_at <= ?", (now,))
        conn.execute(
            """
            INSERT INTO developer_oauth_states (
                state_hash, provider, mode, account_id, code_verifier, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_token_hash(state), provider, mode, account_id, verifier, expires_at, now),
        )
    common = {
        "client_id": client_id,
        "redirect_uri": oauth_redirect_uri(provider),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider == "google":
        common.update({"response_type": "code", "scope": "openid email profile", "prompt": "select_account"})
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(common)
    else:
        common.update({"scope": "read:user user:email"})
        url = "https://github.com/login/oauth/authorize?" + urlencode(common)
    return RedirectResponse(url, status_code=302)


@app.get("/api/developer/oauth/{provider}/callback")
def complete_developer_oauth(
    provider: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        return oauth_result_redirect("cancelled")
    if not code or not state:
        return oauth_result_redirect("expired")
    with db() as conn:
        oauth_state = conn.execute(
            """
            SELECT * FROM developer_oauth_states
            WHERE state_hash = ? AND provider = ? AND expires_at > ?
            LIMIT 1
            """,
            (session_token_hash(state), provider, utc_now()),
        ).fetchone()
        if oauth_state:
            conn.execute("DELETE FROM developer_oauth_states WHERE id = ?", (oauth_state["id"],))
    if not oauth_state:
        return oauth_result_redirect("expired")
    try:
        identity = oauth_provider_identity(provider, code, oauth_state["code_verifier"])
    except HTTPException:
        return oauth_result_redirect("failed")
    if not identity["subject"]:
        return oauth_result_redirect("failed")
    now = utc_now()
    if oauth_state["mode"] == "bind":
        with db() as conn:
            account = conn.execute(
                """
                SELECT * FROM developer_accounts
                WHERE id = ? AND is_active = 1 AND account_status = 'active'
                """,
                (oauth_state["account_id"],),
            ).fetchone()
            if not account:
                return oauth_result_redirect("expired")
            subject_owner = conn.execute(
                "SELECT account_id FROM developer_identities WHERE provider = ? AND provider_subject = ?",
                (provider, identity["subject"]),
            ).fetchone()
            if subject_owner and subject_owner["account_id"] != account["id"]:
                return oauth_result_redirect("conflict")
            existing_provider = conn.execute(
                "SELECT * FROM developer_identities WHERE account_id = ? AND provider = ?",
                (account["id"], provider),
            ).fetchone()
            if existing_provider and existing_provider["provider_subject"] != identity["subject"]:
                return oauth_result_redirect("conflict")
            if existing_provider:
                conn.execute(
                    """
                    UPDATE developer_identities
                    SET provider_login = ?, provider_email = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (identity["login"], identity["email"], now, existing_provider["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO developer_identities (
                        account_id, provider, provider_subject, provider_login,
                        provider_email, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account["id"], provider, identity["subject"], identity["login"],
                        identity["email"], now, now,
                    ),
                )
        maybe_import_oauth_avatar(
            oauth_state["account_id"], provider, identity.get("avatar_url", "")
        )
        return oauth_result_redirect("bound")
    with db() as conn:
        match = conn.execute(
            """
            SELECT a.* FROM developer_identities i
            JOIN developer_accounts a ON a.id = i.account_id
            WHERE i.provider = ? AND i.provider_subject = ?
              AND a.is_active = 1 AND a.account_status = 'active'
            LIMIT 1
            """,
            (provider, identity["subject"]),
        ).fetchone()
        if not match:
            email_match = None
            if identity["email"]:
                email_match = conn.execute(
                    """
                    SELECT id FROM developer_accounts
                    WHERE lower(email) = ? AND is_active = 1 AND account_status = 'active'
                    LIMIT 1
                    """,
                    (identity["email"],),
                ).fetchone()
            return oauth_result_redirect("unbound" if email_match else "not_registered")
        token, _ = create_session(conn, match["id"], request, provider)
        account_id = match["id"]
    maybe_import_oauth_avatar(account_id, provider, identity.get("avatar_url", ""))
    response = oauth_result_redirect("logged_in")
    set_session_cookie(response, token)
    return response


@app.delete("/api/developer/oauth/{provider}")
def unbind_developer_oauth(provider: str, request: Request) -> dict[str, Any]:
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=404, detail="不支持该登录方式")
    account = read_developer_account(request)
    with db() as conn:
        conn.execute(
            "DELETE FROM developer_identities WHERE account_id = ? AND provider = ?",
            (account["id"], provider),
        )
        updated = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?", (account["id"],)
        ).fetchone()
        return public_account(updated, conn)


@app.get("/api/developer/places", response_model=list[Place])
def list_developer_places(request: Request) -> list[dict[str, Any]]:
    account = read_developer_account(request)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM food_places
            WHERE owner_account_id = ?
               OR (
                    owner_account_id IS NULL
                    AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
               )
            ORDER BY updated_at DESC
            """,
            (account["id"], account["author_name"]),
        ).fetchall()
    return [row_to_place(row) for row in rows]


@app.post("/api/developer/places", response_model=Place)
def create_developer_place(payload: PlaceIn, request: Request) -> dict[str, Any]:
    account = read_developer_account(request)
    created = create_place(payload.model_copy(update={"rating_author": account["author_name"]}))
    with db() as conn:
        conn.execute(
            "UPDATE food_places SET owner_account_id = ? WHERE id = ?",
            (account["id"], created["id"]),
        )
        row = conn.execute("SELECT * FROM food_places WHERE id = ?", (created["id"],)).fetchone()
    return row_to_place(row)


def developer_owned_place(place_id: int, account: sqlite3.Row) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute(
            """
            SELECT * FROM food_places
            WHERE id = ?
              AND (
                    owner_account_id = ?
                    OR (
                        owner_account_id IS NULL
                        AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽'))) = lower(trim(?))
                    )
              )
            """,
            (place_id, account["id"], account["author_name"]),
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
    updated = update_place(
        place_id,
        payload.model_copy(update={"rating_author": account["author_name"]}),
    )
    with db() as conn:
        conn.execute(
            "UPDATE food_places SET owner_account_id = ? WHERE id = ?",
            (account["id"], place_id),
        )
    return updated


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


def account_with_place_count(conn: sqlite3.Connection, account_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT a.*,
               (
                   SELECT COUNT(*)
                   FROM food_places p
                   WHERE p.owner_account_id = a.id
                      OR (
                           p.owner_account_id IS NULL
                           AND lower(trim(COALESCE(NULLIF(p.rating_author, ''), '吕俊泽')))
                               = lower(trim(a.author_name))
                      )
               ) AS place_count
        FROM developer_accounts a
        WHERE a.id = ?
        """,
        (account_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="作者账号不存在")
    result = public_account(row, conn)
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
                       WHERE p.owner_account_id = a.id
                          OR (
                               p.owner_account_id IS NULL
                               AND lower(trim(COALESCE(NULLIF(p.rating_author, ''), '吕俊泽')))
                                   = lower(trim(a.author_name))
                          )
                   ) AS place_count
            FROM developer_accounts a
            ORDER BY a.id
            """
        ).fetchall()
        result = []
        for row in rows:
            item = public_account(row, conn)
            item["place_count"] = row["place_count"]
            result.append(item)
        return result


@app.post("/api/admin/authors")
def create_admin_author(payload: DeveloperInvitationIn) -> dict[str, Any]:
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="请先配置邮件服务")
    author_name = payload.author_name.strip()
    email = normalize_email(payload.email, required=True)
    placeholder_username = f"invite_{secrets.token_hex(12)}"
    now = utc_now()
    try:
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO developer_accounts (
                    username, author_name, password_salt, password_hash,
                    must_change_password, is_active, last_login_at, created_at, updated_at,
                    email, email_verified_at, account_status, avatar_filename,
                    password_algorithm, password_updated_at
                )
                VALUES (?, ?, '', '', 0, 1, '', ?, ?, ?, '', 'pending_invite', '', 'argon2id', '')
                """,
                (placeholder_username, author_name, now, now, email),
            )
            account_id = cur.lastrowid
            token = create_one_time_token(conn, "developer_invitations", account_id, timedelta(hours=24))
            account = conn.execute("SELECT * FROM developer_accounts WHERE id = ?", (account_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="作者名或邮箱已存在") from None
    send_activation_email(account, token)
    with db() as conn:
        conn.execute(
            "UPDATE developer_invitations SET sent_at = ? WHERE token_hash = ?",
            (utc_now(), session_token_hash(token)),
        )
        return account_with_place_count(conn, account_id)


@app.put("/api/admin/authors/{account_id}")
def update_admin_author(
    account_id: int,
    payload: DeveloperAccountUpdate,
) -> dict[str, Any]:
    author_name = payload.author_name.strip()
    email = normalize_email(payload.email)
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
                SET author_name = ?, email = ?,
                    email_verified_at = CASE WHEN lower(email) = lower(?) THEN email_verified_at ELSE '' END,
                    is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (author_name, email, email, 1 if payload.is_active else 0, now, account_id),
            )
            if existing["author_name"] != author_name:
                conn.execute(
                    """
                    UPDATE food_places
                    SET rating_author = ?, updated_at = ?
                    WHERE owner_account_id = ?
                       OR (
                            owner_account_id IS NULL
                            AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽')))
                                = lower(trim(?))
                       )
                    """,
                    (author_name, now, account_id, existing["author_name"]),
                )
            if not payload.is_active:
                conn.execute(
                    "DELETE FROM developer_sessions WHERE account_id = ?",
                    (account_id,),
                )
            return account_with_place_count(conn, account_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="作者名或邮箱已存在") from None


@app.delete("/api/admin/authors/{account_id}")
def delete_admin_author(
    account_id: int,
    payload: DeveloperAccountDelete,
) -> dict[str, Any]:
    avatar_filename = ""
    with db() as conn:
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="作者账号不存在")
        if payload.author_name.strip() != account["author_name"]:
            raise HTTPException(status_code=400, detail="作者名确认不匹配，未执行删除")
        place_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM food_places
            WHERE owner_account_id = ?
               OR (
                    owner_account_id IS NULL
                    AND lower(trim(COALESCE(NULLIF(rating_author, ''), '吕俊泽')))
                        = lower(trim(?))
               )
            """,
            (account_id, account["author_name"]),
        ).fetchone()[0]
        if place_count:
            raise HTTPException(
                status_code=409,
                detail=f"该作者仍有 {place_count} 家店，请先停用账号或处理名下店铺",
            )
        avatar_filename = row_value(account, "avatar_filename", "")
        for table in (
            "developer_sessions",
            "developer_invitations",
            "developer_password_resets",
            "developer_identities",
            "developer_oauth_states",
        ):
            conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM developer_accounts WHERE id = ?", (account_id,))
    if avatar_filename:
        (AVATAR_DIR / Path(avatar_filename).name).unlink(missing_ok=True)
    return {
        "deleted": True,
        "id": account_id,
        "author_name": account["author_name"],
    }


@app.post("/api/admin/authors/{account_id}/send-invitation")
def resend_admin_author_invitation(account_id: int) -> dict[str, Any]:
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="请先配置邮件服务")
    with db() as conn:
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="作者账号不存在")
        if not account["email"]:
            raise HTTPException(status_code=400, detail="请先填写作者邮箱")
        token = create_one_time_token(conn, "developer_invitations", account_id, timedelta(hours=24))
    send_activation_email(account, token)
    with db() as conn:
        conn.execute(
            "UPDATE developer_invitations SET sent_at = ? WHERE token_hash = ?",
            (utc_now(), session_token_hash(token)),
        )
        return account_with_place_count(conn, account_id)


@app.post("/api/admin/authors/{account_id}/reset-password")
def reset_admin_author_password(account_id: int) -> dict[str, Any]:
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="请先配置邮件服务")
    with db() as conn:
        account = conn.execute(
            "SELECT * FROM developer_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="作者账号不存在")
        if not account["email"]:
            raise HTTPException(status_code=400, detail="请先填写作者邮箱")
        token = create_one_time_token(conn, "developer_password_resets", account_id, timedelta(hours=1))
    send_password_reset_email(account, token)
    with db() as conn:
        conn.execute(
            "UPDATE developer_password_resets SET sent_at = ? WHERE token_hash = ?",
            (utc_now(), session_token_hash(token)),
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
        owner = conn.execute(
            "SELECT id FROM developer_accounts WHERE lower(trim(author_name)) = lower(trim(?)) LIMIT 1",
            (payload.rating_author,),
        ).fetchone()
        owner_account_id = owner["id"] if owner else None
        cur = conn.execute(
            """
            INSERT INTO food_places (
                map_provider, country_code, coordinate_system,
                provider_poi_id, name, address, lng, lat, city, district,
                provider_category, phone, business_hours, amap_detail_url,
                provider_detail_url,
                my_category, my_categories, rating, rating_author, recommend_level, review_url,
                review_text, tags, note, visited_at,
                cover_image, image_urls, hide_images, is_public, owner_account_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                owner_account_id,
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
        owner = conn.execute(
            "SELECT id FROM developer_accounts WHERE lower(trim(author_name)) = lower(trim(?)) LIMIT 1",
            (payload.rating_author,),
        ).fetchone()
        owner_account_id = owner["id"] if owner else None
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
                is_public = ?, owner_account_id = ?, updated_at = ?
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
                owner_account_id,
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
