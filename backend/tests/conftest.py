import os
import tempfile
from collections.abc import Callable, Iterator

import pytest

os.environ.update(
    ENVIRONMENT="test",
    SECRET_KEY="test-secret-key-0123456789abcdef0123456789",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://factura:factura@localhost:5433/factura_test"
    ),
    COOKIE_SECURE="false",
    STORAGE_DIR=tempfile.mkdtemp(prefix="factura-test-"),
)

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.models
from app.api.deps import get_login_limiter
from app.core.database import Base, engine
from app.core.security import CSRF_COOKIE, CSRF_HEADER
from app.main import app

PASSWORD = "clave-segura-123"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    get_login_limiter.cache_clear()


def _sync_csrf(client: TestClient) -> TestClient:
    client.headers[CSRF_HEADER] = client.cookies.get(CSRF_COOKIE, "")
    return client


@pytest.fixture
def make_client() -> Callable[..., TestClient]:
    """Crea un cliente con sesión iniciada. El primer usuario se registra; los demás requieren registro abierto."""

    def _make(email: str = "carlo@example.com", register: bool = True) -> TestClient:
        client = TestClient(app)
        if register:
            r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": "Carlo"})
            assert r.status_code == 201, r.text
        else:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert r.status_code == 200, r.text
        return _sync_csrf(client)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


@pytest.fixture
def expense_category(client: TestClient) -> dict:
    return next(c for c in client.get("/api/v1/categories").json() if c["name"] == "Servicios")
