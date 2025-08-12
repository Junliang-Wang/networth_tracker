from typing import Dict, List
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from datetime import date
from ..db import get_session
from ..models import Snapshot, FXRate, Account, Category, Balance, InvestmentFlow
from ..utils import compute_snapshot_networth

router = APIRouter(prefix="/snapshots")

@router.get("/", response_class=HTMLResponse)
def list_snapshots(request: Request):
    with get_session() as s:
        snaps = s.exec(select(Snapshot).order_by(Snapshot.snapshot_date)).all()
        enriched = []
        for snap in snaps:
            total, _ = compute_snapshot_networth(s, snap.id) if snap else (0.0, {})
            enriched.append({"snap": snap, "total": total})
    return request.app.state.templates.TemplateResponse("snapshots.html", {"request": request, "snaps": enriched})

@router.get("/new", response_class=HTMLResponse)
def new_snapshot(request: Request):
    with get_session() as s:
        accounts = s.exec(select(Account).where(Account.is_archived == False).order_by(Account.name)).all()
        categories = s.exec(select(Category)).all()
    # currencies used
    currencies = sorted({a.currency_code for a in accounts})
    return request.app.state.templates.TemplateResponse("snapshot_form.html", {
        "request": request,
        "accounts": accounts,
        "categories": categories,
        "currencies": currencies,
        "today": date.today().isoformat()
    })

@router.post("/create")
async def create_snapshot(
    request: Request,
    snapshot_date: str = Form(...),
    base_currency: str = Form(...),
    notes: str = Form(""),
):
    form = await request.form()

    fx_items: Dict[str, float] = {}
    balance_items: Dict[int, float] = {}
    flow_items: Dict[int, Dict[str, float]] = {}

    for k, v in form.items():
        if k.startswith("fx_"):
            cur = k[3:].upper()
            fx_items[cur] = float(v) if v else 0.0
        elif k.startswith("bal_"):
            aid = int(k[4:])
            balance_items[aid] = float(v) if v else 0.0
        elif k.startswith("dep_"):
            aid = int(k[4:])
            flow_items.setdefault(aid, {})["deposit"] = float(v) if v else 0.0
        elif k.startswith("wd_"):
            aid = int(k[3:])
            flow_items.setdefault(aid, {})["withdrawal"] = float(v) if v else 0.0
        elif k.startswith("fee_"):
            aid = int(k[4:])
            flow_items.setdefault(aid, {})["fees"] = float(v) if v else 0.0
        elif k.startswith("div_"):
            aid = int(k[4:])
            flow_items.setdefault(aid, {})["dividends_interest"] = float(v) if v else 0.0
        elif k.startswith("pl_"):
            aid = int(k[3:])
            flow_items.setdefault(aid, {})["realized_pl"] = float(v) if v else 0.0

    from datetime import date as _date
    from ..db import get_session
    from ..models import Snapshot, FXRate, Balance, InvestmentFlow

    with get_session() as s:
        snap = Snapshot(snapshot_date=_date.fromisoformat(snapshot_date),
                        base_currency=base_currency.upper(),
                        notes=notes)
        s.add(snap)
        s.commit()
        s.refresh(snap)

        fx_items[snap.base_currency] = 1.0

        # ensure any account currency has a rate
        acct_curs = {a.currency_code.upper() for a in s.exec(select(Account)).all()}
        missing = {c for c in acct_curs if c != base_currency.upper()} - set(fx_items.keys())
        if missing:
            # You could flash this in UI later; for now raise
            raise ValueError(f"Missing FX rate(s): {', '.join(sorted(missing))}")
        
        for cur, rate in fx_items.items():
            if rate <= 0:
                raise ValueError(f"FX rate for {cur} must be > 0")
            s.add(FXRate(snapshot_id=snap.id, currency_code=cur, rate_to_base=rate))

        for account_id, native_balance in balance_items.items():
            s.add(Balance(snapshot_id=snap.id, account_id=account_id, native_balance=native_balance))

        for account_id, flows in flow_items.items():
            s.add(InvestmentFlow(snapshot_id=snap.id, account_id=account_id,
                                 deposit=flows.get("deposit", 0.0),
                                 withdrawal=flows.get("withdrawal", 0.0),
                                 fees=flows.get("fees", 0.0),
                                 dividends_interest=flows.get("dividends_interest", 0.0),
                                 realized_pl=flows.get("realized_pl", 0.0)))
        s.commit()

    return RedirectResponse(url="/snapshots/", status_code=303)
