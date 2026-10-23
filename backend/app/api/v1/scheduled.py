from fastapi import APIRouter, Depends, status

from app.api.deps import DB, CurrentUser, PathId, verify_csrf
from app.models import ScheduledPayment, Transaction
from app.schemas.scheduled import ScheduledHistory, ScheduledIn, ScheduledOut, ScheduledPayIn, ScheduledUpdate
from app.schemas.support import DeletedOut
from app.schemas.transaction import TransactionOut
from app.services import scheduled

router = APIRouter(prefix="/scheduled-payments", tags=["pagos fijos"], dependencies=[Depends(verify_csrf)])


@router.get("", response_model=list[ScheduledOut])
def list_scheduled(user: CurrentUser, db: DB) -> list[ScheduledPayment]:
    return scheduled.list_payments(db, user)


@router.post("", response_model=ScheduledOut, status_code=status.HTTP_201_CREATED)
def create_scheduled(data: ScheduledIn, user: CurrentUser, db: DB) -> ScheduledPayment:
    return scheduled.create(db, user, data)


@router.patch("/{payment_id}", response_model=ScheduledOut)
def update_scheduled(payment_id: PathId, data: ScheduledUpdate, user: CurrentUser, db: DB) -> ScheduledPayment:
    return scheduled.update(db, user, payment_id, data)


@router.delete("/{payment_id}", response_model=DeletedOut)
def delete_scheduled(payment_id: PathId, user: CurrentUser, db: DB) -> DeletedOut:
    return DeletedOut(trash_id=scheduled.delete(db, user, payment_id))


@router.get("/{payment_id}/history", response_model=ScheduledHistory)
def payment_history(payment_id: PathId, user: CurrentUser, db: DB) -> ScheduledHistory:
    return scheduled.history(db, user, payment_id)


@router.post("/{payment_id}/pay", response_model=TransactionOut)
def pay_scheduled(payment_id: PathId, data: ScheduledPayIn, user: CurrentUser, db: DB) -> Transaction:
    return scheduled.pay(db, user, payment_id, data)
