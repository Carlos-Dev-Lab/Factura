"""Utilidades de meses y fechas (siempre día 1 para representar un mes)."""

import calendar
from datetime import date


def month_range(month: str) -> tuple[date, date]:
    """Primer y último día de un mes "AAAA-MM"."""
    start = month_start(month)
    return start, end_of_month(start)


def month_start(month: str) -> date:
    year, mon = (int(x) for x in month.split("-"))
    return date(year, mon, 1)


def end_of_month(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, months: int) -> date:
    """Suma meses a un día 1 (o ajusta el día al último del mes destino)."""
    index = d.year * 12 + d.month - 1 + months
    year, mon = divmod(index, 12)
    last = calendar.monthrange(year, mon + 1)[1]
    return date(year, mon + 1, min(d.day, last))


def months_between(start: date, end: date) -> int:
    """Cantidad de meses de `start` a `end` (0 si son el mismo mes)."""
    return (end.year - start.year) * 12 + end.month - start.month


def day_in_month(month_first: date, day: int) -> date:
    """El día `day` del mes; el 31 se ajusta al último día de los meses cortos."""
    return month_first.replace(day=min(day, calendar.monthrange(month_first.year, month_first.month)[1]))


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")
