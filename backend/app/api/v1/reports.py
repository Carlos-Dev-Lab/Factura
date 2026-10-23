import os
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from app.api.deps import DB, CurrentUser, Storage
from app.schemas.common import MAX_YEAR, MIN_YEAR, Month
from app.schemas.report import CalendarMonth, FiscalReport, MonthSummary, YearReport
from app.services import export, reports

router = APIRouter(prefix="/reports", tags=["reportes"])

MonthQuery = Annotated[Month, Query(description="Mes en formato AAAA-MM")]


@router.get("/summary", response_model=MonthSummary)
def month_summary(month: MonthQuery, user: CurrentUser, db: DB) -> MonthSummary:
    return reports.summary(db, user, month)


@router.get("/calendar", response_model=CalendarMonth)
def month_calendar(month: MonthQuery, user: CurrentUser, db: DB) -> CalendarMonth:
    return reports.calendar_month(db, user, month)


@router.get("/year", response_model=YearReport)
def year_report(user: CurrentUser, db: DB, year: int = Query(ge=MIN_YEAR, le=MAX_YEAR)) -> YearReport:
    return reports.year_report(db, user, year)


@router.get("/fiscal", response_model=FiscalReport)
def fiscal_report(month: MonthQuery, user: CurrentUser, db: DB) -> FiscalReport:
    return reports.fiscal_report(db, user, month)


@router.get("/fiscal.csv")
def fiscal_csv(month: MonthQuery, user: CurrentUser, db: DB) -> Response:
    return Response(
        content=reports.fiscal_csv(reports.fiscal_report(db, user, month)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="compras_{month}.csv"'},
    )


@router.get("/fiscal.zip")
def fiscal_zip(month: MonthQuery, user: CurrentUser, db: DB, storage: Storage) -> FileResponse:
    path = export.fiscal_zip(db, user, storage, month)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"contador_{month}.zip",
        background=BackgroundTask(os.remove, path),
    )


@router.get("/export.csv")
def export_csv(user: CurrentUser, db: DB, month: Annotated[Month | None, Query()] = None) -> Response:
    filename = f"movimientos_{month or 'todos'}.csv"
    return Response(
        content=reports.export_csv(db, user, month),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
