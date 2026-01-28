import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import auth, utils, entries, users, roles
from app.api import ws
from app.api.deps import get_current_user
from app.models.user import User

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="CE Guests API", version="1.0.0")

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
app.include_router(utils.router, prefix="/api/v1/utils", tags=["utils"])
app.include_router(entries.router, prefix="/api/v1", tags=["entries"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(roles.router, prefix="/api/v1", tags=["roles"])
app.include_router(ws.router, tags=["ws"])


@app.get("/")
def read_root(current_user: User = Depends(get_current_user)):
    return {"message": "CE Guests API"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
