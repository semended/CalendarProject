from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import RESET_TOKEN_TTL, SECRET_KEY, VERIFY_TOKEN_TTL

VERIFY_SALT = "email-verify-v1"
RESET_SALT = "password-reset-v1"


class TokenError(Exception):
    pass


def _s(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt=salt)


def make_verify_token(email: str) -> str:
    return _s(VERIFY_SALT).dumps(email)


def read_verify_token(token: str) -> str:
    try:
        return _s(VERIFY_SALT).loads(token, max_age=VERIFY_TOKEN_TTL)
    except (BadSignature, SignatureExpired) as e:
        raise TokenError(str(e))


def make_reset_token(email: str) -> str:
    return _s(RESET_SALT).dumps(email)


def read_reset_token(token: str) -> str:
    try:
        return _s(RESET_SALT).loads(token, max_age=RESET_TOKEN_TTL)
    except (BadSignature, SignatureExpired) as e:
        raise TokenError(str(e))
