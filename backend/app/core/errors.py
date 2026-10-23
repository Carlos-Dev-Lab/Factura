"""Errores de dominio. Los servicios los lanzan y la API los traduce a HTTP."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404

    def __init__(self, what: str = "Recurso") -> None:
        super().__init__(f"{what} no encontrado")


class ConflictError(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422


class AuthError(DomainError):
    status_code = 401


class ForbiddenError(DomainError):
    status_code = 403


class TooManyRequestsError(DomainError):
    status_code = 429


class PayloadTooLargeError(DomainError):
    status_code = 413


class NotConfiguredError(DomainError):
    """Una función opcional que el servidor no tiene configurada (por ejemplo, el envío de emails)."""

    status_code = 404


class UpstreamError(DomainError):
    """Falló un servicio externo (Google, el servidor de correo)."""

    status_code = 502
