from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

from sqlmodel import SQLModel, Session, create_engine

engine = None
_db_path: Optional[Path] = None

def _sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.as_posix()}"

def init_db(data_folder: Optional[Path] = None, *, filename: str = "networth.sqlite") -> None:
    """Create or connect the DB at the given folder."""
    global engine, _db_path
    if data_folder is None:
        data_folder = Path.cwd() / "data"
    data_folder.mkdir(parents=True, exist_ok=True)
    _db_path = data_folder / filename
    engine = create_engine(_sqlite_url(_db_path), echo=False, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

def reset_db(new_folder: Path, *, filename: str = "networth.sqlite") -> None:
    """Switch the engine to a new folder (Settings → Choose…)."""
    global engine
    # dispose old engine (safe even if None)
    try:
        if engine is not None:
            engine.dispose()
    except Exception:
        pass
    init_db(new_folder, filename=filename)

@contextmanager
def get_session():
    if engine is None:
        raise RuntimeError("DB engine not initialized; call init_db() in startup.")
    with Session(engine) as session:
        yield session

def current_db_path() -> Optional[Path]:
    return _db_path
