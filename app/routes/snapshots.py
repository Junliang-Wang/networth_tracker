from typing import Dict, List
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select, delete  # <-- delete added
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

@router.get("/{snapshot_id}/edit", response_class=HTMLResponse)
def edit_snapshot(request: Request, snapshot_id: int):
    with get_session() as s:
        snap = s.get(Snapshot, snapshot_id)
        if not snap:
            return RedirectResponse(url="/snapshots/", status_code=303)

        # include ALL accounts (archived + active)
        accounts = s.exec(select(Account).order_by(Account.name)).all()
        categories = s.exec(select(Category)).all()

        # existing FX on this snapshot
        prefill_fx = {r.currency_code: r.rate_to_base
                      for r in s.exec(select(FXRate).where(FXRate.snapshot_id == snapshot_id)).all()}

        # balances + flows prefills
        prefill_bal = {b.account_id: b.native_balance
                       for b in s.exec(select(Balance).where(Balance.snapshot_id == snapshot_id)).all()}
        flows = s.exec(select(InvestmentFlow).where(InvestmentFlow.snapshot_id == snapshot_id)).all()
        prefill_flow = {
            f.account_id: dict(deposit=f.deposit, withdrawal=f.withdrawal, fees=f.fees,
                               dividends_interest=f.dividends_interest, realized_pl=f.realized_pl)
            for f in flows
        }

        # union: currencies from accounts + saved FX (exclude base)
        acct_curs = {a.currency_code for a in accounts}
        saved_curs = set(prefill_fx.keys())
        currencies = sorted((acct_curs | saved_curs) - {snap.base_currency})

    return request.app.state.templates.TemplateResponse(
        "snapshot_edit.html",
        {
            "request": request,
            "snap": snap,
            "accounts": accounts,
            "categories": categories,
            "currencies": currencies,
            "prefill_fx": prefill_fx,
            "prefill_bal": prefill_bal,
            "prefill_flow": prefill_flow,
        },
    )


@router.post("/{snapshot_id}/update")
async def update_snapshot(
    snapshot_id: int,
    request: Request,
    snapshot_date: str = Form(...),
    base_currency: str = Form(...),
    notes: str = Form(""),
):
    form = await request.form()

    fx_items, balance_items, flow_items = {}, {}, {}

    for k, v in form.items():
        if k.startswith("fx_"):
            fx_items[k[3:].upper()] = float(v) if v else 0.0
        elif k.startswith("bal_"):
            balance_items[int(k[4:])] = float(v) if v else 0.0
        elif k.startswith("dep_"):
            aid = int(k[4:]); flow_items.setdefault(aid, {})["deposit"] = float(v) if v else 0.0
        elif k.startswith("wd_"):
            aid = int(k[3:]); flow_items.setdefault(aid, {})["withdrawal"] = float(v) if v else 0.0
        elif k.startswith("fee_"):
            aid = int(k[4:]); flow_items.setdefault(aid, {})["fees"] = float(v) if v else 0.0
        elif k.startswith("div_"):
            aid = int(k[4:]); flow_items.setdefault(aid, {})["dividends_interest"] = float(v) if v else 0.0
        elif k.startswith("pl_"):
            aid = int(k[3:]); flow_items.setdefault(aid, {})["realized_pl"] = float(v) if v else 0.0

    with get_session() as s:
        snap = s.get(Snapshot, snapshot_id)
        if not snap:
            return RedirectResponse(url="/snapshots/", status_code=303)

        # update meta
        snap.snapshot_date = date.fromisoformat(snapshot_date)
        snap.base_currency = base_currency.upper()
        snap.notes = notes
        s.add(snap)
        s.commit()

        # --- merge FX: existing + new form values ---
        prev_fx = {
            r.currency_code: r.rate_to_base
            for r in s.exec(select(FXRate).where(FXRate.snapshot_id == snapshot_id)).all()
        }
        merged_fx = {**prev_fx, **fx_items}          # form overrides prior
        merged_fx[snap.base_currency] = 1.0          # base is always 1.0

        # clear old rows (manual cascade)
        s.exec(delete(FXRate).where(FXRate.snapshot_id == snapshot_id))
        s.exec(delete(Balance).where(Balance.snapshot_id == snapshot_id))
        s.exec(delete(InvestmentFlow).where(InvestmentFlow.snapshot_id == snapshot_id))

        # re-insert FX
        for cur, rate in merged_fx.items():
            if cur == snap.base_currency:
                rate = 1.0
            if rate <= 0:
                raise ValueError(f"FX rate for {cur} must be > 0")
            s.add(FXRate(snapshot_id=snapshot_id, currency_code=cur, rate_to_base=rate))

        # re-insert balances
        for account_id, native_balance in balance_items.items():
            s.add(Balance(snapshot_id=snapshot_id, account_id=account_id, native_balance=native_balance))

        # re-insert flows
        for account_id, flows in flow_items.items():
            s.add(InvestmentFlow(snapshot_id=snapshot_id, account_id=account_id,
                                deposit=flows.get("deposit", 0.0),
                                withdrawal=flows.get("withdrawal", 0.0),
                                fees=flows.get("fees", 0.0),
                                dividends_interest=flows.get("dividends_interest", 0.0),
                                realized_pl=flows.get("realized_pl", 0.0)))
        s.commit()


    return RedirectResponse(url="/snapshots/", status_code=303)

@router.post("/{snapshot_id}/delete")
def delete_snapshot(snapshot_id: int):
    with get_session() as s:
        if not s.get(Snapshot, snapshot_id):
            return RedirectResponse(url="/snapshots/", status_code=303)
        s.exec(delete(FXRate).where(FXRate.snapshot_id == snapshot_id))
        s.exec(delete(Balance).where(Balance.snapshot_id == snapshot_id))
        s.exec(delete(InvestmentFlow).where(InvestmentFlow.snapshot_id == snapshot_id))
        s.exec(delete(Snapshot).where(Snapshot.id == snapshot_id))
        s.commit()
    return RedirectResponse(url="/snapshots/", status_code=303)
