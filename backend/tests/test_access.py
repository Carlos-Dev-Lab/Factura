"""Control de acceso: sesión obligatoria, CSRF en todo lo que modifica y aislamiento entre usuarios.

Las dos primeras pruebas recorren TODAS las rutas de la API, así una ruta nueva que olvide la
sesión o el token CSRF hace fallar las pruebas sin tener que acordarse de agregarla acá.
"""

import io
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import config
from app.core.security import CSRF_COOKIE, CSRF_HEADER
from app.main import app

TODAY = date.today().isoformat()
MONTH = date.today().strftime("%Y-%m")

# Rutas que se usan sin sesión (o que solo cierran la sesión).
PUBLIC = {
    "/api/health",
    "/api/v1/auth/config",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    # Ida y vuelta con Google: la vuelta se valida con la cookie firmada de estado (test_google.py).
    "/api/v1/auth/google/start",
    "/api/v1/auth/google/callback",
}
# Rutas que, sin sesión, no deberían requerir CSRF: el formulario de ingreso y el de registro.
NO_CSRF = {"/api/v1/auth/register", "/api/v1/auth/login"}


def _routes() -> list[tuple[str, str]]:
    # Desde el esquema OpenAPI: incluye las rutas de todos los routers anidados.
    out = []
    for raw_path, methods in app.openapi()["paths"].items():
        path = re.sub(r"\{file_key\}", "0" * 32 + ".png", raw_path)
        path = re.sub(r"\{[^}]+\}", "1", path)
        out += [(method.upper(), path) for method in methods]
    assert len(out) > 50, "no se encontraron las rutas de la API"
    return out


ROUTES = _routes()


def _anonymous_with_csrf() -> TestClient:
    """Sin sesión, pero con el par cookie/cabecera CSRF correcto: así se prueba solo la sesión."""
    anon = TestClient(app)
    anon.cookies.set(CSRF_COOKIE, "token-de-prueba")
    anon.headers[CSRF_HEADER] = "token-de-prueba"
    return anon


@pytest.mark.parametrize(("method", "path"), [r for r in ROUTES if r[1] not in PUBLIC])
def test_every_route_requires_a_session(client: TestClient, method: str, path: str) -> None:
    r = _anonymous_with_csrf().request(method, path, params={"month": MONTH, "year": 2026})
    assert r.status_code == 401, f"{method} {path} respondió {r.status_code} sin sesión"


@pytest.mark.parametrize(("method", "path"), [r for r in ROUTES if r[0] != "GET" and r[1] not in NO_CSRF])
def test_every_change_requires_the_csrf_token(client: TestClient, method: str, path: str) -> None:
    no_header = TestClient(app)
    no_header.cookies = client.cookies  # sesión válida, pero sin la cabecera (como un formulario de otro sitio)
    assert no_header.request(method, path).status_code == 403, f"{method} {path} sin cabecera CSRF"
    no_header.headers[CSRF_HEADER] = "otro-valor"
    assert no_header.request(method, path).status_code == 403, f"{method} {path} con CSRF distinto"


def test_login_form_from_another_site_is_not_accepted() -> None:
    # Un formulario HTML de otro sitio no puede mandar JSON: llega como texto o como formulario.
    anon = TestClient(app)
    body = '{"email": "a@example.com", "password": "clave-segura-123"}'
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        r = anon.post("/api/v1/auth/login", content=body, headers={"Content-Type": content_type})
        assert r.status_code == 422, content_type


def test_session_cookie_is_protected(make_client) -> None:
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "clave-segura-123"})
    cookies = [h for k, h in r.headers.multi_items() if k == "set-cookie"]
    session = next(c for c in cookies if c.startswith("factura_session="))
    assert "HttpOnly" in session and "SameSite=strict" in session
    # Ni el hash ni su nombre (has_password, en cambio, es un dato público de la propia cuenta).
    assert "password_hash" not in r.text and "$argon2" not in r.text


def test_profile_ignores_fields_it_does_not_own(client: TestClient) -> None:
    before = client.get("/api/v1/auth/me").json()
    r = client.patch(
        "/api/v1/auth/me", json={"id": 99, "email": "x@example.com", "password_hash": "x", "session_version": 9}
    )
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").json() == before


# ---------- Aislamiento entre usuarios ----------


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "PNG")
    return buf.getvalue()


def _owner_data(owner: TestClient) -> dict:
    cats = {c["name"]: c["id"] for c in owner.get("/api/v1/categories").json()}
    cash = owner.get("/api/v1/accounts").json()[0]["id"]
    bank = owner.post("/api/v1/accounts", json={"name": "Banco", "type": "bank", "opening_balance": 1_000_000}).json()
    tx = owner.post(
        "/api/v1/transactions",
        json={"amount": 5000, "date": TODAY, "category_id": cats["Comidas"], "account_id": bank["id"]},
    ).json()
    key = owner.post("/api/v1/invoices/analyze", files={"file": ("f.png", _png(), "image/png")}).json()["file_key"]
    inv = owner.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 90_000, "file_key": key}).json()
    sp = owner.post(
        "/api/v1/scheduled-payments",
        json={"name": "Alquiler", "amount": 1_000, "day_of_month": 5, "start_month": MONTH, "account_id": bank["id"]},
    ).json()
    rule = owner.post(
        "/api/v1/categories/rules", json={"pattern": "biggie", "category_id": cats["Supermercado"]}
    ).json()
    transfer = owner.post(
        "/api/v1/accounts/transfers",
        json={"from_account_id": bank["id"], "to_account_id": cash, "amount": 100, "date": TODAY},
    ).json()
    gone = owner.post("/api/v1/transactions", json={"amount": 1, "date": TODAY}).json()
    trash_id = owner.delete(f"/api/v1/transactions/{gone['id']}").json()["trash_id"]
    return {
        "cat": cats["Comidas"], "bank": bank["id"], "tx": tx["id"], "key": key, "inv": inv["id"],
        "sp": sp["id"], "rule": rule["id"], "transfer": transfer["id"], "trash": trash_id,
    }  # fmt: skip


def _snapshot(owner: TestClient) -> dict:
    return {
        path: owner.get(path).json()
        for path in (
            "/api/v1/transactions", "/api/v1/invoices", "/api/v1/scheduled-payments", "/api/v1/categories",
            "/api/v1/categories/rules", "/api/v1/accounts", "/api/v1/accounts/transfers", "/api/v1/trash",
        )
    }  # fmt: skip


def test_users_cannot_see_or_touch_each_others_data(make_client, monkeypatch) -> None:
    owner = make_client()
    d = _owner_data(owner)
    before = _snapshot(owner)
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    intruder = make_client("intruso@example.com")
    own_cash = intruder.get("/api/v1/accounts").json()[0]["id"]

    # Listados: no aparece nada del otro usuario.
    assert intruder.get("/api/v1/transactions").json()["total"] == 0
    assert intruder.get("/api/v1/transactions", params={"account_id": d["bank"]}).json()["total"] == 0
    assert intruder.get("/api/v1/transactions", params={"category_id": d["cat"]}).json()["total"] == 0
    for path in ("/api/v1/invoices", "/api/v1/scheduled-payments", "/api/v1/categories/rules", "/api/v1/trash",
                 "/api/v1/accounts/transfers"):  # fmt: skip
        assert intruder.get(path).json() == [], path
    assert [a["id"] for a in intruder.get("/api/v1/accounts").json()] == [own_cash]
    assert d["cat"] not in {c["id"] for c in intruder.get("/api/v1/categories").json()}

    # Leer, editar, borrar o accionar sobre lo ajeno: 404, como si no existiera.
    attempts = [
        ("GET", f"/api/v1/invoices/{d['inv']}/file", None),
        ("GET", f"/api/v1/scheduled-payments/{d['sp']}/history", None),
        ("PATCH", f"/api/v1/transactions/{d['tx']}", {"amount": 1}),
        ("PATCH", f"/api/v1/invoices/{d['inv']}", {"total": 1}),
        ("PATCH", f"/api/v1/scheduled-payments/{d['sp']}", {"amount": 1}),
        ("PATCH", f"/api/v1/categories/{d['cat']}", {"name": "Robada"}),
        ("PATCH", f"/api/v1/accounts/{d['bank']}", {"name": "Robada"}),
        ("POST", f"/api/v1/invoices/{d['inv']}/pay", {}),
        ("POST", f"/api/v1/invoices/{d['inv']}/unpay", None),
        ("POST", f"/api/v1/scheduled-payments/{d['sp']}/pay", {"month": MONTH}),
        ("POST", f"/api/v1/trash/{d['trash']}/restore", None),
        ("DELETE", f"/api/v1/trash/{d['trash']}", None),
        ("DELETE", f"/api/v1/transactions/{d['tx']}", None),
        ("DELETE", f"/api/v1/invoices/{d['inv']}", None),
        ("DELETE", f"/api/v1/scheduled-payments/{d['sp']}", None),
        ("DELETE", f"/api/v1/categories/{d['cat']}", None),
        ("DELETE", f"/api/v1/categories/rules/{d['rule']}", None),
        ("DELETE", f"/api/v1/accounts/{d['bank']}", None),
        ("DELETE", f"/api/v1/accounts/transfers/{d['transfer']}", None),
    ]
    for method, path, body in attempts:
        r = intruder.request(method, path, json=body)
        assert r.status_code == 404, f"{method} {path} respondió {r.status_code}"

    # Usar ids ajenos dentro de datos propios: rechazado.
    references = [
        ("/api/v1/transactions", {"amount": 1, "date": TODAY, "category_id": d["cat"]}),
        ("/api/v1/transactions", {"amount": 1, "date": TODAY, "account_id": d["bank"]}),
        (
            "/api/v1/accounts/transfers",
            {"from_account_id": d["bank"], "to_account_id": own_cash, "amount": 1, "date": TODAY},
        ),
        (
            "/api/v1/accounts/transfers",
            {"from_account_id": own_cash, "to_account_id": d["bank"], "amount": 1, "date": TODAY},
        ),
        ("/api/v1/invoices", {"total": 1, "category_id": d["cat"]}),
        ("/api/v1/invoices", {"total": 1, "file_key": d["key"]}),
        ("/api/v1/invoices", {"total": 1, "already_paid": True, "account_id": d["bank"]}),
        ("/api/v1/scheduled-payments", {"name": "x", "amount": 1, "day_of_month": 1, "category_id": d["cat"]}),
        ("/api/v1/scheduled-payments", {"name": "x", "amount": 1, "day_of_month": 1, "account_id": d["bank"]}),
        ("/api/v1/categories/rules", {"pattern": "abc", "category_id": d["cat"]}),
        (
            "/api/v1/imports/commit",
            {"account_id": d["bank"], "items": [{"date": TODAY, "amount": 1, "kind": "expense"}]},
        ),
        (
            "/api/v1/imports/commit",
            {"items": [{"date": TODAY, "amount": 1, "kind": "expense", "category_id": d["cat"]}]},
        ),
    ]
    for path, body in references:
        r = intruder.post(path, json=body)
        assert r.status_code in (404, 422), f"POST {path} {body} respondió {r.status_code}"
    assert intruder.get("/api/v1/transactions").json()["total"] == 0

    # "Descartar" el archivo de otro no lo borra (cada usuario tiene su carpeta).
    assert intruder.delete(f"/api/v1/invoices/uploads/{d['key']}").status_code == 204
    assert owner.get(f"/api/v1/invoices/{d['inv']}/file").status_code == 200

    # Los datos del dueño siguen exactamente iguales.
    assert _snapshot(owner) == before


def test_json_responses_cannot_run_anything(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["cache-control"] == "no-store"


def test_allowed_hosts_rejects_other_domains(monkeypatch) -> None:
    from app.main import create_app

    monkeypatch.setattr(config.get_settings(), "allowed_hosts", "mi-pc.tu-red.ts.net")
    guarded = TestClient(create_app())
    assert guarded.get("/api/health", headers={"Host": "mi-pc.tu-red.ts.net"}).status_code == 200
    assert guarded.get("/api/health", headers={"Host": "localhost:8080"}).status_code == 200
    assert guarded.get("/api/health", headers={"Host": "sitio-malicioso.com"}).status_code == 400


def test_without_allowed_hosts_any_name_works(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me", headers={"Host": "192.168.0.10:8080"}).status_code == 200


def test_three_people_on_one_server_never_mix_data(make_client, monkeypatch) -> None:
    """Tres personas: la segunda repite nombres, RUC y montos de la primera; la tercera no tiene nada."""
    import zipfile

    from app.services import notify

    ana = make_client()
    _owner_data(ana)  # una de cada cosa: cuenta, movimiento, factura con archivo, pago fijo, regla, papelera
    j = lambda r: r.json()  # noqa: E731
    secret = "A-SECRETO-NO-COMPARTIR"
    ana.post("/api/v1/transactions", json={"amount": 77_000, "date": TODAY, "description": secret})
    invoice = {"supplier": secret, "ruc": "80000519-8", "number": "001-001-0000123", "total": 95_000}
    ana.post("/api/v1/invoices", json={**invoice, "issue_date": TODAY, "due_date": TODAY, "iva10": 8_636})
    endpoint = "https://fcm.googleapis.com/fcm/send/dispositivo-de-ana"
    monkeypatch.setattr(notify, "_allowed_endpoint", lambda e: True)
    ana.post("/api/v1/notifications/push", json={"endpoint": endpoint, "keys": {"p256dh": "x", "auth": "y"}})
    before = _snapshot(ana)
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    beto = make_client("beto@example.com")
    caro = make_client("caro@example.com")

    # Mismos nombres que Ana: se permiten, son de otra persona.
    assert beto.post("/api/v1/categories", json={"name": "Mascotas"}).status_code == 201
    assert beto.post("/api/v1/accounts", json={"name": "Banco", "type": "bank"}).status_code == 201
    # La misma factura (RUC y número) no figura como "ya cargada": la de Ana no cuenta.
    r = beto.post("/api/v1/invoices", json={"supplier": "ESSAP", "ruc": "80000519-8", "number": "001-001-0000123",
                                            "total": 95_000, "issue_date": TODAY})  # fmt: skip
    assert r.status_code == 201, r.text
    # Las reglas y el historial de Ana no le sugieren nada a Beto.
    beto_cats = {c["id"] for c in j(beto.get("/api/v1/categories"))}
    sug = j(beto.get("/api/v1/categories/suggest", params={"text": "biggie", "ruc": "80000519-8"}))
    assert sug["category_id"] is None or sug["category_id"] in beto_cats
    assert sug["source"] not in ("regla", "historial", "ruc") or sug["category_id"] in beto_cats
    # Importar un extracto con un movimiento igual a uno de Ana no lo marca como repetido.
    day = date.today().strftime("%d/%m/%Y")
    rows = j(
        beto.post(
            "/api/v1/imports/preview",
            files={"file": ("e.csv", f"Fecha;Concepto;Débito\n{day};X;5.000\n".encode(), "text/csv")},
        )
    )["rows"]
    assert rows[0]["duplicate"] is False

    # Reportes, avisos y exportaciones de Beto y Caro: nada de Ana.
    for who in (beto, caro):
        summary = j(who.get("/api/v1/reports/summary", params={"month": MONTH}))
        assert summary["expense"] == 0 and summary["income"] == 0
        assert secret not in str(summary) and "ANDE" not in str(summary)
        assert all(
            day_["dues"] == [] or secret not in str(day_)
            for day_ in j(who.get("/api/v1/reports/calendar", params={"month": MONTH}))["days"]
        )
        assert j(who.get("/api/v1/reports/year", params={"year": date.today().year}))["expense"] == 0
        assert secret not in who.get("/api/v1/reports/fiscal.csv", params={"month": MONTH}).text
        assert secret not in who.get("/api/v1/reports/export.csv").text
        assert all(secret not in a["title"] and "ANDE" not in a["title"] for a in j(who.get("/api/v1/alerts")))
        dump = zipfile.ZipFile(io.BytesIO(who.get("/api/v1/export/full.zip").content))
        everything = b"".join(dump.read(n) for n in dump.namelist())
        assert secret.encode() not in everything and b"ana" not in everything.lower().replace(b"banana", b"")
        fiscal = zipfile.ZipFile(io.BytesIO(who.get("/api/v1/reports/fiscal.zip", params={"month": MONTH}).content))
        assert all(not n.startswith("facturas/") or who is beto for n in fiscal.namelist())
        assert j(who.get("/api/v1/transactions", params={"q": "SECRETO"}))["total"] == 0
        assert j(who.get("/api/v1/invoices", params={"q": "SECRETO"})) == []
    assert j(caro.get("/api/v1/invoices")) == [] and j(caro.get("/api/v1/transactions"))["total"] == 0

    # Acciones masivas o por valor (no por id) de Beto no tocan lo de Ana.
    assert beto.delete("/api/v1/trash").status_code == 204  # vaciar SU papelera
    beto.post("/api/v1/notifications/push/remove", json={"endpoint": endpoint})  # el dispositivo de Ana
    assert beto.post("/api/v1/auth/logout-all").status_code == 204  # cierra las sesiones de Beto, no las de Ana
    assert ana.get("/api/v1/auth/me").status_code == 200
    assert j(ana.get("/api/v1/notifications/settings"))["push_devices"] == 1
    assert len(j(ana.get("/api/v1/trash"))) == 1

    # Ana sigue teniendo exactamente lo mismo y ve lo suyo en sus exportaciones.
    assert _snapshot(ana) == before
    assert secret in ana.get("/api/v1/reports/export.csv").text


def test_logout_everywhere_stops_notifications_on_every_device(client: TestClient, monkeypatch) -> None:
    from app.services import notify

    monkeypatch.setattr(notify, "_allowed_endpoint", lambda e: True)
    for n in range(2):
        client.post(
            "/api/v1/notifications/push",
            json={"endpoint": f"https://fcm.googleapis.com/fcm/send/{n}", "keys": {"p256dh": "x", "auth": "y"}},
        )
    assert client.get("/api/v1/notifications/settings").json()["push_devices"] == 2
    client.post("/api/v1/auth/logout-all")
    from app.core.database import SessionLocal
    from app.models import PushSubscription

    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 0  # el celular perdido ya no recibe nada


def test_only_the_server_admin_sees_the_backups(make_client, monkeypatch) -> None:
    admin = make_client()
    assert admin.get("/api/v1/system/backups").status_code == 200
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    other = make_client("otra@example.com")
    assert other.get("/api/v1/system/backups").status_code == 403
