"""Punto de entrada de la API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import DeadlockDetected, LockNotAvailable
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from starlette.datastructures import MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.errors import DomainError
from app.core.validation import spanish_errors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


class NoStoreMiddleware:
    """Las respuestas de la API tienen datos privados: ningún navegador, proxy o CDN debe guardarlas.

    Sin esto, un CDN delante de la app podría cachear, por ejemplo, /api/v1/reports/export.csv
    (por su extensión) y entregarle los movimientos de una persona a otra.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers.setdefault("Vary", "Cookie")
                # Un JSON abierto directamente en el navegador nunca puede cargar ni ejecutar nada.
                if headers.get("content-type", "").startswith("application/json"):
                    headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            await send(message)

        await self.app(scope, receive, send_with_header)


def create_app() -> FastAPI:
    settings = get_settings()
    is_dev = settings.environment == "development"
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="2.1.0",
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
    )
    app.add_middleware(NoStoreMiddleware)
    if hosts := settings.allowed_host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # En español y sin devolver lo enviado (podría ser una contraseña).
        return JSONResponse({"detail": spanish_errors(list(exc.errors()))}, status_code=422)

    # Red de seguridad: si un dato llega a la base sin pasar por una validación (un número fuera
    # de rango en un filtro, un choque entre dos pedidos simultáneos), se responde con un mensaje
    # claro en vez de un error 500. La transacción ya se revirtió en get_db.
    @app.exception_handler(DataError)
    async def data_error_handler(request: Request, exc: DataError) -> JSONResponse:
        logger.warning("Dato rechazado por la base en %s %s: %s", request.method, request.url.path, exc.orig)
        return JSONResponse({"detail": "Algún dato está fuera de rango o no es válido"}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Conflicto en la base en %s %s: %s", request.method, request.url.path, exc.orig)
        return JSONResponse({"detail": "Ese cambio choca con otro dato. Recargá y volvé a probar."}, status_code=409)

    @app.exception_handler(OperationalError)
    async def operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        # Dos pedidos que se bloquean mutuamente: PostgreSQL cancela uno. Se puede reintentar.
        if isinstance(exc.orig, DeadlockDetected | LockNotAvailable):
            logger.warning("Bloqueo en la base en %s %s", request.method, request.url.path)
            return JSONResponse({"detail": "Hubo otro cambio al mismo tiempo. Volvé a probar."}, status_code=409)
        raise exc

    @app.get("/api/health", tags=["sistema"])
    def health() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
