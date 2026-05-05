from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.database import engine
from app.routers.health import router as health_router
from app.routers.me import router as me_router
from app.routers.score_github import router as score_github_router
from app.routers.user import router as user_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Devplanet API",
    lifespan=lifespan,
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(health_router)
api_v1.include_router(me_router)
api_v1.include_router(score_github_router)
api_v1.include_router(user_router)
app.include_router(api_v1)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "devplanet-api"}
