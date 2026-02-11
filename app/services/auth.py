import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pytz import timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models.refresh_token import RefreshToken

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Декодирование JWT токена"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_timestamp() -> str:
    """Получить текущий timestamp в ISO формате"""
    tz = timezone(settings.TIMEZONE)
    return datetime.now(tz).isoformat()


def generate_refresh_token() -> str:
    """Генерация случайного refresh token"""
    return secrets.token_urlsafe(32)


def generate_refresh_token_lookup_hash(token: str) -> str:
    """Быстрый детерминированный хеш для поиска refresh token в БД"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_refresh_token(token: str) -> str:
    """Хеширование refresh token (используем тот же контекст что и для паролей)"""
    return pwd_context.hash(token)


def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:
    """Проверка refresh token"""
    return pwd_context.verify(plain_token, hashed_token)


def create_refresh_token_db(
    db: Session,
    user_id: str,
    refresh_token: str,
    commit: bool = True,
) -> RefreshToken:
    """Создание записи refresh token в БД"""
    tz = timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    expires_at = now + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)
    
    token_lookup_hash = generate_refresh_token_lookup_hash(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    
    db_token = RefreshToken(
        user_id=user_id,
        token_lookup_hash=token_lookup_hash,
        token_hash=token_hash,
        expires_at=expires_at.isoformat(),
        created_at=now.isoformat(),
        revoked=0
    )
    db.add(db_token)
    if commit:
        db.commit()
        db.refresh(db_token)
    return db_token


def find_refresh_token(db: Session, user_id: str, refresh_token: str) -> Optional[RefreshToken]:
    """Поиск refresh token в БД по user_id и проверка валидности"""
    lookup_hash = generate_refresh_token_lookup_hash(refresh_token)
    token = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == 0,
        RefreshToken.token_lookup_hash == lookup_hash,
    ).first()

    if not token:
        return None
    if not verify_refresh_token(refresh_token, token.token_hash):
        return None
    if _is_refresh_token_expired(token.expires_at):
        return None
    return token


def _is_refresh_token_expired(expires_at_raw: str) -> bool:
    expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone("UTC"))

    tz = timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    return expires_at <= now


def _find_refresh_token_legacy_scan(db: Session, refresh_token: str) -> Optional[RefreshToken]:
    """Fallback для старых записей без token_lookup_hash."""
    legacy_tokens = db.query(RefreshToken).filter(
        RefreshToken.revoked == 0,
        RefreshToken.token_lookup_hash.is_(None),
    ).all()
    for token in legacy_tokens:
        if verify_refresh_token(refresh_token, token.token_hash) and not _is_refresh_token_expired(token.expires_at):
            return token
    return None


def find_refresh_token_by_token(db: Session, refresh_token: str) -> Optional[RefreshToken]:
    """Поиск refresh token в БД по самому токену (без user_id)"""
    lookup_hash = generate_refresh_token_lookup_hash(refresh_token)
    token = db.query(RefreshToken).filter(
        RefreshToken.revoked == 0,
        RefreshToken.token_lookup_hash == lookup_hash,
    ).first()
    if token and verify_refresh_token(refresh_token, token.token_hash) and not _is_refresh_token_expired(token.expires_at):
        return token

    # Совместимость с уже выданными токенами до миграции.
    return _find_refresh_token_legacy_scan(db, refresh_token)


def revoke_refresh_token(db: Session, refresh_token_obj: RefreshToken, commit: bool = True) -> None:
    """Инвалидация refresh token"""
    refresh_token_obj.revoked = 1
    if commit:
        db.commit()


def cleanup_expired_tokens(db: Session, user_id: Optional[str] = None, commit: bool = True) -> int:
    """Очистка истекших и отозванных токенов. Возвращает количество удаленных токенов"""
    tz = timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    now_iso = now.isoformat()
    
    query = db.query(RefreshToken).filter(
        (RefreshToken.expires_at < now_iso) | (RefreshToken.revoked == 1)
    )
    
    if user_id:
        query = query.filter(RefreshToken.user_id == user_id)
    
    deleted = query.delete(synchronize_session=False)
    if commit:
        db.commit()
    return deleted
