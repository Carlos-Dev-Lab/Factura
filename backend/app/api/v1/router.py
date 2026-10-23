from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    auth,
    categories,
    data,
    google,
    invoices,
    notifications,
    reports,
    scheduled,
    transactions,
)

api_router = APIRouter(prefix="/api/v1")
for module in (auth, google, categories, transactions, invoices, scheduled, reports, accounts, notifications, data):
    api_router.include_router(module.router)
