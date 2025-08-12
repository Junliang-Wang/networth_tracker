from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import init_db
from .routes import dashboard, accounts, snapshots


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    # Seed categories if empty
    from sqlmodel import Session, select
    from .db import engine
    from .models import Category
    with Session(engine) as s:
        if not s.exec(select(Category)).first():
            for name in ["Liquidity", "Investments", "Properties", "Liabilities"]:
                s.add(Category(name=name))
            s.commit()
    yield
    # Shutdown (nothing needed now)


def create_app() -> FastAPI:
    app = FastAPI(title="networth", version="0.1.0", lifespan=lifespan)

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    templates = Jinja2Templates(directory=str(templates_dir))
    app.state.templates = templates

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routes
    app.include_router(dashboard.router)
    app.include_router(accounts.router)
    app.include_router(snapshots.router)

    return app


app = create_app()
