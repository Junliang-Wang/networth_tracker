from pathlib import Path
from contextlib import asynccontextmanager
import os, json
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import CONFIG_FILE           # <-- use shared module
from .db import init_db
from .routes import dashboard, accounts, snapshots
from .routes import settings as settings_routes

# Make CONFIG_FILE importable by settings.py
CONFIG_FILE = Path.home() / ".networth_config.json"

def _resolve_data_dir() -> Path:
    env_dir = os.getenv("NETWORTH_DATA_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        if p.exists() and p.is_dir():
            return p
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            saved = Path(data.get("data_dir", "")).expanduser().resolve()
            if saved.exists() and saved.is_dir():
                return saved
        except Exception:
            pass
    # Fallback default (no GUI prompt anymore since you want a button in UI)
    p = (Path.cwd() / "data").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

DATA_FOLDER = _resolve_data_dir()
print(f"📁 Using data folder: {DATA_FOLDER}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DATA_FOLDER)
    app.state.data_folder = DATA_FOLDER
    from sqlmodel import Session, select
    from .db import engine
    from .models import Category
    with Session(engine) as s:
        if not s.exec(select(Category)).first():
            for name in ["Liquidity", "Investments", "Properties", "Liabilities"]:
                s.add(Category(name=name))
            s.commit()
    yield

def create_app() -> FastAPI:
    app = FastAPI(title="networth", version="0.1.0", lifespan=lifespan)
    base_dir = Path(__file__).parent
    templates_dir = base_dir / "templates"
    static_dir = base_dir / "static"; static_dir.mkdir(parents=True, exist_ok=True)

    templates = Jinja2Templates(directory=str(templates_dir))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(dashboard.router)
    app.include_router(accounts.router)
    app.include_router(snapshots.router)
    app.include_router(settings_routes.router)     # <-- add

    # optional shared filter
    def format_currency(value: float) -> str:
        try: return "{:,.2f}".format(float(value))
        except Exception: return str(value)
    app.state.templates.env.filters["currency"] = format_currency
    return app

app = create_app()
