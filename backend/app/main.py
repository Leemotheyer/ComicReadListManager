from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings as env_settings
from app.services.app_settings import SettingsStore
from app.database import init_db
from app.routers import backup, comicvine, komga, lists, locg, missing, settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(env_settings.data_dir).mkdir(parents=True, exist_ok=True)
    env_settings.exports_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Comic Read List Manager", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lists.router)
app.include_router(locg.router)
app.include_router(komga.router)
app.include_router(comicvine.router)
app.include_router(settings.router)
app.include_router(backup.router)
app.include_router(missing.router)


@app.get("/api/health")
def health():
    s = SettingsStore.cached()
    return {
        "status": "ok",
        "comicvine_configured": bool(s.comicvine_api_key),
        "kapowarr_configured": bool(s.kapowarr_url and s.kapowarr_api_key),
        "komga_configured": bool(s.komga_url and s.komga_api_key),
    }


def _mount_frontend(app: FastAPI) -> None:
    if not STATIC_DIR.is_dir():
        return

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        if full_path:
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404)


_mount_frontend(app)
