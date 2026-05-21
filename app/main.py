from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.error_handlers import (
    register_auth_oauth_exception_handlers,
    register_github_exception_handlers,
)
from app.database import engine
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.me import router as me_router
from app.routers.onboarding import router as onboarding_router
from app.routers.score_github import router as score_github_router
from app.routers.user import router as user_router
from app.routers.xp import router as xp_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


_settings = get_settings()

app = FastAPI(
    title="Devplanet API",
    lifespan=lifespan,
)

register_auth_oauth_exception_handlers(app)
register_github_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(health_router)
api_v1.include_router(auth_router)
api_v1.include_router(me_router)
api_v1.include_router(onboarding_router)
api_v1.include_router(score_github_router)
api_v1.include_router(user_router)
api_v1.include_router(xp_router)
app.include_router(api_v1)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "devplanet-api"}
