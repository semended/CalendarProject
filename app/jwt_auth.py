"""JWT access tokens для /api/v1/*.

Подпись HMAC-SHA256 тем же SECRET_KEY, что и cookie-сессии. TTL 7 дней.
Отдельно от `app/tokens.py` (там itsdangerous для одноразовых email-ссылок)."""
import time
from typing import Optional

import jwt

from app.config import SECRET_KEY

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 дней


def encode_access_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Возвращает user_id если токен валидный, иначе None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
