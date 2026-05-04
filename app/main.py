from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Devplanet API",
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "devplanet-api"}
