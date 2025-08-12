from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Iterable, Optional, Tuple

from sqlmodel import Session, select
from .models import Snapshot, FXRate, Account, Balance, Category

def compute_snapshot_networth(session: Session, snapshot_id: int) -> Tuple[float, Dict[str, float]]:
    """Return (total_networth_base, totals_by_category_base)."""
    snap = session.get(Snapshot, snapshot_id)
    assert snap, "Snapshot not found"
    # FX dict
    fx_rows = session.exec(select(FXRate).where(FXRate.snapshot_id == snapshot_id)).all()
    fx: Dict[str, float] = {r.currency_code.upper(): r.rate_to_base for r in fx_rows}
    fx[snap.base_currency.upper()] = 1.0

    total = 0.0
    by_cat: Dict[str, float] = {"Liquidity": 0.0, "Investments": 0.0, "Properties": 0.0, "Liabilities": 0.0}

    rows = session.exec(
        select(Balance, Account, Category)
        .join(Account, Account.id == Balance.account_id)
        .join(Category, Category.id == Account.category_id)
        .where(Balance.snapshot_id == snapshot_id)
    ).all()

    for bal, acct, cat in rows:
        rate = fx.get(acct.currency_code.upper())
        if rate is None:
            raise ValueError(f"Missing FX rate for {acct.currency_code} in snapshot {snapshot_id}")
        base_val = bal.native_balance * rate
        sign = -1.0 if cat.name.lower() == "liabilities" else 1.0
        by_cat[cat.name] = by_cat.get(cat.name, 0.0) + sign * base_val
        total += sign * base_val

    return total, by_cat

def find_snapshot_12m_prior(session: Session, snapshot_id: int) -> Optional[int]:
    snap = session.get(Snapshot, snapshot_id)
    if not snap:
        return None
    target_year = snap.snapshot_date.year - 1
    target_month = snap.snapshot_date.month
    # Find the snapshot with the latest date <= target year-month
    rows = session.exec(select(Snapshot).order_by(Snapshot.snapshot_date)).all()
    prior = [s for s in rows if (s.snapshot_date.year < snap.snapshot_date.year or
                                 (s.snapshot_date.year == target_year and s.snapshot_date.month <= target_month) or
                                 (s.snapshot_date.year == target_year and s.snapshot_date.month == target_month and s.snapshot_date <= snap.snapshot_date))]
    if not prior:
        return None
    # Choose the snapshot closest to (year-1, same month) but not after
    candidate = None
    for s in rows:
        if (s.snapshot_date.year < snap.snapshot_date.year or
            (s.snapshot_date.year == target_year and s.snapshot_date.month <= target_month)):
            candidate = s
    return candidate.id if candidate else None
