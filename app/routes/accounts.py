from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select, delete
from ..db import get_session
from ..models import Account, Category, Tag, AccountTag, Balance, InvestmentFlow
from sqlalchemy import func, or_

router = APIRouter(prefix="/accounts")

@router.get("/", response_class=HTMLResponse)
def list_accounts(request: Request):
    with get_session() as s:
        accounts = s.exec(select(Account).order_by(Account.name)).all()
        cats = s.exec(select(Category)).all()
        cat_map = {c.id: c.name for c in cats}
        tags = s.exec(select(Tag)).all()
    # read optional ?error=... message
    error = request.query_params.get("error")
    return request.app.state.templates.TemplateResponse(
        "accounts.html",
        {
            "request": request,
            "accounts": accounts,
            "categories": cats,
            "cat_map": cat_map,
            "tags": tags,
            "error": error,
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


@router.get("/edit/{account_id}", response_class=HTMLResponse)
def edit_account(request: Request, account_id: int):
    with get_session() as s:
        acct = s.get(Account, account_id)
        if not acct:
            return RedirectResponse(url="/accounts/?error=Account+not+found", status_code=303)
        cats = s.exec(select(Category)).all()
        tag_names = [
            t.name
            for t in s.exec(
                select(Tag)
                .join(AccountTag, AccountTag.tag_id == Tag.id)
                .where(AccountTag.account_id == account_id)
            ).all()
        ]
    return request.app.state.templates.TemplateResponse(
        "account_edit.html",
        {"request": request, "acct": acct, "categories": cats, "tags_csv": ", ".join(tag_names)},
    )


@router.post("/update/{account_id}")
def update_account(
    account_id: int,
    name: str = Form(...),
    category_id: int = Form(...),
    currency_code: str = Form(...),
    tags: str = Form(""),
    notes: str = Form(""),
    is_archived: str = Form("off"),
):
    with get_session() as s:
        acct = s.get(Account, account_id)
        if not acct:
            return RedirectResponse(url="/accounts/?error=Account+not+found", status_code=303)

        acct.name = name
        acct.category_id = int(category_id)
        acct.currency_code = currency_code.upper()
        acct.notes = notes
        acct.is_archived = (is_archived == "on")
        s.add(acct)
        s.commit()

        # replace tag set
        for link in s.exec(select(AccountTag).where(AccountTag.account_id == account_id)).all():
            s.delete(link)
        if tags.strip():
            for raw in [t.strip() for t in tags.split(",") if t.strip()]:
                tag = s.exec(select(Tag).where(Tag.name == raw)).first()
                if not tag:
                    tag = Tag(name=raw)
                    s.add(tag)
                    s.commit()
                    s.refresh(tag)
                s.add(AccountTag(account_id=account_id, tag_id=tag.id))
        s.commit()

    return RedirectResponse(url="/accounts/", status_code=303)


@router.post("/unarchive/{account_id}")
def unarchive_account(account_id: int):
    with get_session() as s:
        acct = s.get(Account, account_id)
        if acct:
            acct.is_archived = False
            s.add(acct)
            s.commit()
    return RedirectResponse(url="/accounts/", status_code=303)


@router.post("/delete/{account_id}")
def delete_account(account_id: int):
    with get_session() as s:
        acct = s.get(Account, account_id)
        if not acct:
            return RedirectResponse(url="/accounts/?error=Account+not+found", status_code=303)

        # only count NON-ZERO usage
        has_bal = s.exec(
            select(func.count(Balance.account_id)).where(
                Balance.account_id == account_id,
                Balance.native_balance != 0
            )
        ).one()
        has_flow = s.exec(
            select(func.count(InvestmentFlow.account_id)).where(
                InvestmentFlow.account_id == account_id,
                or_(
                    InvestmentFlow.deposit != 0,
                    InvestmentFlow.withdrawal != 0,
                    InvestmentFlow.fees != 0,
                    InvestmentFlow.dividends_interest != 0,
                    InvestmentFlow.realized_pl != 0,
                )
            )
        ).one()

        if has_bal or has_flow:
            return RedirectResponse(
                url="/accounts/?error=Cannot+delete+this+account:+it+has+non-zero+balances/flows.+Archive+instead.",
                status_code=303,
            )

        # clean up zero-only references first
        s.exec(delete(Balance).where(Balance.account_id == account_id))
        s.exec(delete(InvestmentFlow).where(InvestmentFlow.account_id == account_id))
        s.exec(delete(AccountTag).where(AccountTag.account_id == account_id))  # <-- remove tag links

        # finally delete the account
        s.delete(acct)
        s.commit()

    return RedirectResponse(url="/accounts/?error=Account+deleted", status_code=303)
