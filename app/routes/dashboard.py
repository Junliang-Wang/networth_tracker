from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select
from ..db import get_session
from ..models import Snapshot
from ..utils import compute_snapshot_networth, find_snapshot_12m_prior

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as s:
        snaps = s.exec(select(Snapshot).order_by(Snapshot.snapshot_date)).all()
        if not snaps:
            return request.app.state.templates.TemplateResponse("dashboard_empty.html", {"request": request})
        # Build series
        points = []
        for snap in snaps:
            total, _ = compute_snapshot_networth(s, snap.id)
            points.append({"date": snap.snapshot_date.isoformat(), "total": round(total, 2), "base": snap.base_currency})
        # Current and 12m change
        current = points[-1]["total"]
        prior_id = find_snapshot_12m_prior(s, snaps[-1].id)
        delta_abs = delta_pct = None
        if prior_id:
            prior_total, _ = compute_snapshot_networth(s, prior_id)
            delta_abs = round(current - prior_total, 2)
            if prior_total != 0:
                delta_pct = round(100.0 * (current - prior_total) / prior_total, 2)
        return request.app.state.templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "points": points,
                "current": current,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "base": snaps[-1].base_currency,
            },
        )
