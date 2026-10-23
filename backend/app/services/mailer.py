"""Envío de emails por SMTP con una cuenta del servidor (por ejemplo, Gmail con contraseña de aplicación).

Siempre cifrado: SSL directo en el puerto 465 o STARTTLS en los demás, verificando el
certificado del servidor. Si el servidor no ofrece TLS no se envía nada, para no mandar la
contraseña en claro.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import get_settings

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 15


class _NoTLSError(Exception):
    pass


def available() -> bool:
    return get_settings().email_enabled


def build_message(to: str, subject: str, text: str) -> EmailMessage:
    """Mensaje de texto plano. EmailMessage rechaza saltos de línea en las cabeceras (ValueError)."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or formataddr(("Factura", s.smtp_user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=s.smtp_user.rpartition("@")[2] or None)
    # Aviso automático: los programas de correo no responden con "fuera de la oficina".
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    return msg


def send_mail(to: str, subject: str, text: str) -> bool:
    """Envía un email. Devuelve False (y lo registra) si no está configurado o si falla."""
    if not available():
        return False
    s = get_settings()
    try:
        msg = build_message(to, subject, text)
        context = ssl.create_default_context()
        if s.smtp_port == 465:
            with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS, context=context) as smtp:
                smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS) as smtp:
                smtp.ehlo()
                if not smtp.has_extn("starttls"):
                    raise _NoTLSError("el servidor no ofrece STARTTLS")
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError, ValueError, _NoTLSError) as exc:
        # El mensaje del servidor nunca incluye la contraseña.
        logger.warning("No se pudo enviar un email (%s): %s", type(exc).__name__, exc)
        return False
