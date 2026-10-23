"""Avisos por email: verificación de la dirección con código, límites y envío seguro por SMTP."""

import re
import smtplib
import ssl
from datetime import date, datetime
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import config
from app.core.database import SessionLocal
from app.models import User
from app.services import mailer, notify

EMAIL = "/api/v1/notifications/email"
SETTINGS = "/api/v1/notifications/settings"


class Outbox(list):
    def code(self) -> str:
        match = re.search(r"\b(\d{6})\b", self[-1][2])
        assert match, self[-1][2]
        return match.group(1)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    s = config.get_settings()
    monkeypatch.setattr(s, "smtp_user", "factura.avisos@gmail.com")
    monkeypatch.setattr(s, "smtp_password", "abcd efgh ijkl mnop")
    sent = Outbox()

    def fake_send(to: str, subject: str, text: str) -> bool:
        sent.append((to, subject, text))
        return True

    monkeypatch.setattr(mailer, "send_mail", fake_send)
    return sent


def test_email_channel_needs_server_configuration(client: TestClient) -> None:
    assert client.get(SETTINGS).json()["email_available"] is False
    r = client.post(EMAIL, json={"address": "carlo@example.com"})
    assert r.status_code == 404 and "configurado" in r.json()["detail"]


def test_address_is_confirmed_with_a_code(client: TestClient, outbox: Outbox) -> None:
    r = client.post(EMAIL, json={"address": "Carlo.Avisos@Example.com"})
    assert r.status_code == 200 and r.json() == {"verified": False}
    to, subject, text = outbox[-1]
    assert to == "carlo.avisos@example.com"
    code = outbox.code()
    assert code not in subject  # el código no se ve en la vista previa de la notificación
    s = client.get(SETTINGS).json()
    assert s["email_available"] is True and s["email_pending"] == "carlo.avisos@example.com"
    assert s["email_enabled"] is False and s["email_address"] is None
    # Todavía no se puede activar sin dirección confirmada.
    assert client.patch(SETTINGS, json={"email_enabled": True}).status_code == 422

    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"{EMAIL}/confirm", json={"code": wrong}).status_code == 422
    assert client.post(f"{EMAIL}/confirm", json={"code": "12ab56"}).status_code == 422  # solo 6 dígitos
    ok = client.post(f"{EMAIL}/confirm", json={"code": code})
    assert ok.status_code == 200
    assert ok.json()["email_enabled"] is True and ok.json()["email_address"] == "carlo.avisos@example.com"
    # Un solo uso.
    assert client.post(f"{EMAIL}/confirm", json={"code": code}).status_code == 422

    assert client.patch(SETTINGS, json={"email_enabled": False}).json()["email_enabled"] is False
    assert client.patch(SETTINGS, json={"email_enabled": True}).json()["email_enabled"] is True


def test_code_is_cancelled_after_five_wrong_attempts(client: TestClient, outbox: Outbox) -> None:
    client.post(EMAIL, json={"address": "carlo@example.com"})
    code = outbox.code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        assert client.post(f"{EMAIL}/confirm", json={"code": wrong}).status_code == 422
    assert client.post(f"{EMAIL}/confirm", json={"code": wrong}).status_code == 429
    # Ni el código correcto sirve ya.
    assert client.post(f"{EMAIL}/confirm", json={"code": code}).status_code in (422, 429)
    assert client.get(SETTINGS).json()["email_pending"] is None
    # Con un código nuevo se vuelve a empezar.
    client.post(EMAIL, json={"address": "carlo@example.com"})
    assert client.post(f"{EMAIL}/confirm", json={"code": outbox.code()}).status_code == 200


def test_code_requests_are_limited(client: TestClient, outbox: Outbox) -> None:
    for _ in range(3):
        assert client.post(EMAIL, json={"address": "victima@example.com"}).status_code == 200
    assert client.post(EMAIL, json={"address": "victima@example.com"}).status_code == 429
    assert len(outbox) == 3  # nadie usa el servidor para llenar de correos una dirección ajena


def test_code_only_confirms_its_own_account_and_address(client: TestClient, make_client, outbox, monkeypatch) -> None:
    client.post(EMAIL, json={"address": "carlo@example.com"})
    code = outbox.code()
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    other = make_client("beto@example.com")
    other.post(EMAIL, json={"address": "beto@example.com"})
    # El código de Carlo no sirve en la cuenta de Beto (salvo que coincidan por azar).
    if code != outbox.code():
        assert other.post(f"{EMAIL}/confirm", json={"code": code}).status_code == 422


def test_google_email_needs_no_code(client: TestClient, outbox: Outbox) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User))
        user.google_email = "carlo@gmail.com"
        db.commit()
    r = client.post(EMAIL, json={"address": "carlo@gmail.com"})
    assert r.json() == {"verified": True} and outbox == []
    s = client.get(SETTINGS).json()
    assert s["email_enabled"] is True and s["email_address"] == "carlo@gmail.com"


def test_remove_email(client: TestClient, outbox: Outbox) -> None:
    client.post(EMAIL, json={"address": "carlo@example.com"})
    client.post(f"{EMAIL}/confirm", json={"code": outbox.code()})
    assert client.delete(EMAIL).status_code == 204
    s = client.get(SETTINGS).json()
    assert s["email_enabled"] is False and s["email_address"] is None and s["email_pending"] is None


def test_alerts_and_test_message_are_sent_by_email(client: TestClient, outbox: Outbox) -> None:
    client.post(EMAIL, json={"address": "carlo@example.com"})
    client.post(f"{EMAIL}/confirm", json={"code": outbox.code()})
    outbox.clear()

    r = client.post("/api/v1/notifications/test").json()
    assert r["email_sent"] is True and outbox[-1][0] == "carlo@example.com"
    assert "Ajustes → Avisos" in outbox[-1][2]  # cómo dejar de recibirlos

    client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 231_500, "due_date": "2020-01-10"})
    now = datetime.combine(date.today(), datetime.min.time()).replace(hour=9)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert notify.has_channel(db, user)  # el email solo ya es un canal
        assert notify.run_digest(db, user, now) == 1
        db.commit()
    assert "ANDE" in outbox[-1][2] and outbox[-1][1].startswith("Factura:")


# ---------- SMTP ----------


def test_message_rejects_header_injection(monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "smtp_user", "factura.avisos@gmail.com")
    with pytest.raises(ValueError):
        mailer.build_message("carlo@example.com", "Hola\r\nBcc: todos@example.com", "texto").as_string()
    msg = mailer.build_message("carlo@example.com", "Factura: aviso", "<script>alert(1)</script>")
    assert msg.get_content_type() == "text/plain"  # sin HTML: nada se interpreta


class _FakeSMTP:
    instances: ClassVar[list["_FakeSMTP"]] = []
    offers_tls = True

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.calls: list[str] = []
        self.context: ssl.SSLContext | None = None
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def has_extn(self, name: str) -> bool:
        return self.offers_tls

    def starttls(self, context: ssl.SSLContext) -> None:
        self.context = context
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")

    def send_message(self, msg: object) -> None:
        self.calls.append("send")


@pytest.fixture
def fake_smtp(monkeypatch) -> type[_FakeSMTP]:
    s = config.get_settings()
    monkeypatch.setattr(s, "smtp_user", "factura.avisos@gmail.com")
    monkeypatch.setattr(s, "smtp_password", "abcd efgh ijkl mnop")
    _FakeSMTP.instances = []
    _FakeSMTP.offers_tls = True
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def test_smtp_always_uses_verified_tls_before_the_password(fake_smtp) -> None:
    assert mailer.send_mail("carlo@example.com", "Factura: aviso", "texto") is True
    smtp = fake_smtp.instances[-1]
    assert smtp.calls.index("starttls") < smtp.calls.index("login") < smtp.calls.index("send")
    assert smtp.context.verify_mode == ssl.CERT_REQUIRED and smtp.context.check_hostname is True


def test_smtp_without_tls_never_sends_the_password(fake_smtp) -> None:
    fake_smtp.offers_tls = False
    assert mailer.send_mail("carlo@example.com", "Factura: aviso", "texto") is False
    assert "login" not in fake_smtp.instances[-1].calls


def test_smtp_failure_is_reported_without_the_password(fake_smtp, monkeypatch, caplog) -> None:
    def refuse(self, user: str, password: str) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(_FakeSMTP, "login", refuse)
    assert mailer.send_mail("carlo@example.com", "Factura: aviso", "texto") is False
    assert "SMTPAuthenticationError" in caplog.text and "abcd efgh" not in caplog.text
