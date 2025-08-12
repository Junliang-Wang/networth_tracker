from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from ..db import get_session
from ..models import Account, Category, Tag, AccountTag

router = APIRouter(prefix="/accounts")

@router.get("/", response_class=HTMLResponse)
def list_accounts(request: Request):
    with get_session() as s:
        accounts = s.exec(select(Account).order_by(Account.name)).all()
        cats = s.exec(select(Category)).all()           # keep the full list
        cat_map = {c.id: c.name for c in cats}         # for display
        tags = s.exec(select(Tag)).all()
    return request.app.state.templates.TemplateResponse(
        "accounts.html",
        {
            "request": request,
            "accounts": accounts,
            "categories": cats,    # <-- this was missing
            "cat_map": cat_map,
            "tags": tags,
        },
    )

@router.post("/create")
def create_account(
    name: str = Form(...),
    category_id: int = Form(...),
    currency_code: str = Form(...),
    tags: str = Form(""),
    notes: str = Form("")
):
    with get_session() as s:
        acct = Account(name=name, category_id=category_id, currency_code=currency_code.upper(), notes=notes)
        s.add(acct)
        s.commit()
        s.refresh(acct)
        # tags: comma-separated
        if tags.strip():
            for raw in [t.strip() for t in tags.split(",")]:
                if not raw:
                    continue
                tag = s.exec(select(Tag).where(Tag.name == raw)).first()
                if not tag:
                    tag = Tag(name=raw)
                    s.add(tag)
                    s.commit()
                    s.refresh(tag)
                s.add(AccountTag(account_id=acct.id, tag_id=tag.id))
        s.commit()
    return RedirectResponse(url="/accounts/", status_code=303)

@router.post("/archive/{account_id}")
def archive_account(account_id: int):
    with get_session() as s:
        acct = s.get(Account, account_id)
        if acct:
            acct.is_archived = True
            s.add(acct)
            s.commit()
    return RedirectResponse(url="/accounts/", status_code=303)
