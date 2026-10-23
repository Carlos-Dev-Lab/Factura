from datetime import date

from fastapi import APIRouter, Depends, status

from app.api.deps import DB, CurrentUser, PathId, verify_csrf
from app.schemas.account import AccountIn, AccountOut, AccountUpdate, TransferIn, TransferOut
from app.services import accounts

router = APIRouter(prefix="/accounts", tags=["cuentas"], dependencies=[Depends(verify_csrf)])


@router.get("", response_model=list[AccountOut])
def list_accounts(user: CurrentUser, db: DB) -> list[AccountOut]:
    return accounts.list_accounts(db, user)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(data: AccountIn, user: CurrentUser, db: DB) -> AccountOut:
    return accounts.create(db, user, data)


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    user: CurrentUser,
    db: DB,
    start: date | None = None,
    end: date | None = None,
    account_id: int | None = None,
) -> list[TransferOut]:
    return accounts.list_transfers(db, user, start=start, end=end, account_id=account_id)


@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
def create_transfer(data: TransferIn, user: CurrentUser, db: DB) -> TransferOut:
    return accounts.create_transfer(db, user, data)


@router.delete("/transfers/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(transfer_id: PathId, user: CurrentUser, db: DB) -> None:
    accounts.delete_transfer(db, user, transfer_id)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: PathId, data: AccountUpdate, user: CurrentUser, db: DB) -> AccountOut:
    return accounts.update(db, user, account_id, data)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: PathId, user: CurrentUser, db: DB) -> None:
    accounts.delete(db, user, account_id)
