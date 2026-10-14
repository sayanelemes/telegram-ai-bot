from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import api_router
from app.config.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nutrition & Expense AI Mini App",
        description="FastAPI Backend for Telegram Mini App and Google Gemini AI Assistant",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(api_router)

    # Serve static frontend files if built
    static_path = Path(settings.STATIC_DIR)
    if not static_path.is_absolute():
        project_root = Path(__file__).resolve().parent.parent.parent
        static_path = project_root / static_path

    if static_path.exists() and (static_path / "index.html").exists():
        assets_dir = static_path / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str, request: Request):
            # Don't intercept /api routes
            if full_path.startswith("api"):
                return None
            target_file = static_path / full_path
            if target_file.is_file():
                return FileResponse(target_file)
            return FileResponse(static_path / "index.html")

    return app
