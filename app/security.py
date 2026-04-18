from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def is_hashed(password: str) -> bool:
    return password.startswith("$2a$") or password.startswith("$2b$") or password.startswith("$2y$")


def verify_password(plain: str, stored: str) -> bool:
    if is_hashed(stored):
        try:
            return pwd_context.verify(plain, stored)
        except Exception:
            return False
    # legacy plaintext record — constant-time-ish equality
    return plain == stored
