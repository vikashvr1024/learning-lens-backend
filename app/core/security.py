from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def create_access_token(user_id: str, settings: Settings) -> str:
    expires = datetime.now(UTC) + timedelta(hours=8)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> str | None:
    try:
        return str(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"])
    except (JWTError, KeyError):
        return None

