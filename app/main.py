import logging
import asyncio
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import auth, entries, users, roles, settings as settings_router, visit_goals, reasons, reference_data
from app.api import ws
from app.api.deps import get_current_user
from app.database import SessionLocal
from app.models.user import User
from app.services.auth import cleanup_expired_tokens

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="CE Guests API", version="1.0.0")
logger = logging.getLogger(__name__)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(entries.router, prefix="/api/v1", tags=["entries"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(roles.router, prefix="/api/v1", tags=["roles"])
app.include_router(settings_router.router, prefix="/api/v1", tags=["settings"])
app.include_router(visit_goals.router, prefix="/api/v1", tags=["visit_goals"])
app.include_router(reasons.router, prefix="/api/v1", tags=["reasons"])
app.include_router(reference_data.router, prefix="/api/v1", tags=["reference_data"])
app.include_router(ws.router, tags=["ws"])


async def token_cleanup_worker():
    interval = settings.TOKEN_CLEANUP_INTERVAL_SECONDS
    if interval <= 0:
        logger.info("Фоновая очистка токенов отключена (TOKEN_CLEANUP_INTERVAL_SECONDS <= 0)")
        return

    logger.info(
        "Запущен фоновый воркер очистки refresh токенов, интервал: %s сек",
        interval,
    )
    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            deleted_count = cleanup_expired_tokens(db)
            if deleted_count:
                logger.info("Фоновая очистка refresh токенов: удалено %s записей", deleted_count)
        except Exception:
            logger.exception("Ошибка фоновой очистки refresh токенов")
        finally:
            db.close()


@app.on_event("startup")
async def startup_background_tasks():
    app.state.token_cleanup_task = asyncio.create_task(token_cleanup_worker())


@app.on_event("shutdown")
async def shutdown_background_tasks():
    task = getattr(app.state, "token_cleanup_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.get("/")
def read_root(current_user: User = Depends(get_current_user)):
    return {"message": "CE Guests API"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
