from datetime import date, datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

# --- Core tables ---

class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    accounts: List["Account"] = Relationship(back_populates="category")


class AccountTag(SQLModel, table=True):
    account_id: int = Field(foreign_key="account.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)


class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    # back_populates must match Account.tags
    accounts: List["Account"] = Relationship(back_populates="tags", link_model=AccountTag)


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category_id: int = Field(foreign_key="category.id")
    currency_code: str = Field(min_length=3, max_length=3)
    notes: Optional[str] = None
    is_archived: bool = Field(default=False)

    category: Optional[Category] = Relationship(back_populates="accounts")
    # back_populates must match Tag.accounts
    tags: List[Tag] = Relationship(back_populates="accounts", link_model=AccountTag)


class Snapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_date: date
    base_currency: str = Field(min_length=3, max_length=3, default="AUD")
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FXRate(SQLModel, table=True):
    snapshot_id: int = Field(foreign_key="snapshot.id", primary_key=True)
    currency_code: str = Field(min_length=3, max_length=3, primary_key=True)
    rate_to_base: float


class Balance(SQLModel, table=True):
    snapshot_id: int = Field(foreign_key="snapshot.id", primary_key=True)
    account_id: int = Field(foreign_key="account.id", primary_key=True)
    native_balance: float = 0.0
    note: Optional[str] = None


class InvestmentFlow(SQLModel, table=True):
    snapshot_id: int = Field(foreign_key="snapshot.id", primary_key=True)
    account_id: int = Field(foreign_key="account.id", primary_key=True)
    deposit: float = 0.0  # required (can be 0)
    withdrawal: float = 0.0
    fees: float = 0.0
    dividends_interest: float = 0.0
    realized_pl: float = 0.0
