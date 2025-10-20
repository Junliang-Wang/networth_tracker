from pathlib import Path
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..db import reset_db, current_db_path
from ..config import CONFIG_FILE          # <-- no more import from main

router = APIRouter(prefix="/settings")

@router.get("/", response_class=HTMLResponse)
def settings_page(request: Request):
    cur = current_db_path()
    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {"request": request, "data_folder": str(cur.parent) if cur else "—", "db_file": str(cur) if cur else "—"},
    )

@router.post("/choose")
def choose_data_folder():
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    chosen = filedialog.askdirectory(title="Select folder to store/load your Networth data")
    root.destroy()
    if not chosen:
        return RedirectResponse(url="/settings/?msg=No+folder+selected", status_code=303)

    folder = Path(chosen).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)

    # persist for next startup
    CONFIG_FILE.write_text(json.dumps({"data_dir": str(folder)}))

    # swap DB engine now
    reset_db(folder)

    return RedirectResponse(url="/settings/?msg=Folder+set+to+" + str(folder).replace(" ", "+"), status_code=303)
