from sqlmodel import SQLModel, create_engine, Session, text
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "networth.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

def init_db() -> None:
    # enable WAL and reasonable pragmas
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    SQLModel.metadata.create_all(engine)

def get_session() -> Session:
    return Session(engine)
