from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, CurrentUser, PathId, verify_csrf
from app.models import Transaction, TransactionKind
from app.schemas.support import DeletedOut
from app.schemas.transaction import TransactionIn, TransactionOut, TransactionPage, TransactionUpdate
from app.services import transactions

router = APIRouter(prefix="/transactions", tags=["movimientos"], dependencies=[Depends(verify_csrf)])


@router.get("", response_model=TransactionPage)
def list_transactions(
    user: CurrentUser,
    db: DB,
    start: date | None = None,
    end: date | None = None,
    kind: TransactionKind | None = None,
    q: str | None = Query(None, max_length=80),
    account_id: int | None = None,
    category_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> TransactionPage:
    items, total, expense_total, income_total = transactions.list_transactions(
        db,
        user,
        start=start,
        end=end,
        kind=kind,
        q=q,
        limit=limit,
        offset=offset,
        account_id=account_id,
        category_id=category_id,
    )
    return TransactionPage(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        expense_total=expense_total,
        income_total=income_total,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(data: TransactionIn, user: CurrentUser, db: DB) -> Transaction:
    return transactions.create(db, user, data)


@router.patch("/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: PathId, data: TransactionUpdate, user: CurrentUser, db: DB) -> Transaction:
    return transactions.update(db, user, tx_id, data)


@router.delete("/{tx_id}", response_model=DeletedOut)
def delete_transaction(tx_id: PathId, user: CurrentUser, db: DB) -> DeletedOut:
    return DeletedOut(trash_id=transactions.delete(db, user, tx_id))
