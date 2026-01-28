import secrets
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


def hash_refresh_token(token: str) -> str:
    """Хеширование refresh token (используем тот же контекст что и для паролей)"""
    return pwd_context.hash(token)


def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:
    """Проверка refresh token"""
    return pwd_context.verify(plain_token, hashed_token)


def create_refresh_token_db(db: Session, user_id: str, refresh_token: str) -> RefreshToken:
    """Создание записи refresh token в БД"""
    tz = timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    expires_at = now + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)
    
    token_hash = hash_refresh_token(refresh_token)
    
    db_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at.isoformat(),
        created_at=now.isoformat(),
        revoked=0
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


def find_refresh_token(db: Session, user_id: str, refresh_token: str) -> Optional[RefreshToken]:
    """Поиск refresh token в БД по user_id и проверка валидности"""
    # Получаем все неотозванные токены пользователя
    tokens = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == 0
    ).all()
    
    # Проверяем каждый токен
    for token in tokens:
        if verify_refresh_token(refresh_token, token.token_hash):
            # Проверяем срок действия
            expires_at = datetime.fromisoformat(token.expires_at.replace('Z', '+00:00'))
            if expires_at.tzinfo is None:
                # Если нет timezone, считаем что это UTC
                expires_at = expires_at.replace(tzinfo=timezone('UTC'))
            
            tz = timezone(settings.TIMEZONE)
            now = datetime.now(tz)
            
            if expires_at > now:
                return token
    
    return None


def find_refresh_token_by_token(db: Session, refresh_token: str) -> Optional[RefreshToken]:
    """Поиск refresh token в БД по самому токену (без user_id)"""
    # Получаем все неотозванные токены
    tokens = db.query(RefreshToken).filter(RefreshToken.revoked == 0).all()
    
    # Проверяем каждый токен
    for token in tokens:
        if verify_refresh_token(refresh_token, token.token_hash):
            # Проверяем срок действия
            expires_at = datetime.fromisoformat(token.expires_at.replace('Z', '+00:00'))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone('UTC'))
            
            tz = timezone(settings.TIMEZONE)
            now = datetime.now(tz)
            
            if expires_at > now:
                return token
    
    return None


def revoke_refresh_token(db: Session, refresh_token_obj: RefreshToken) -> None:
    """Инвалидация refresh token"""
    refresh_token_obj.revoked = 1
    db.commit()


def cleanup_expired_tokens(db: Session, user_id: Optional[str] = None) -> int:
    """Очистка истекших и отозванных токенов. Возвращает количество удаленных токенов"""
    tz = timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    now_iso = now.isoformat()
    
    query = db.query(RefreshToken).filter(
        (RefreshToken.expires_at < now_iso) | (RefreshToken.revoked == 1)
    )
    
    if user_id:
        query = query.filter(RefreshToken.user_id == user_id)
    
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    
    return count
