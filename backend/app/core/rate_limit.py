"""Limitador de intentos de inicio de sesión guardado en PostgreSQL.

Los intentos se cuentan en la base de datos, así el límite se cumple aunque el
backend corra con varios procesos (WEB_CONCURRENCY) o varias réplicas. Cada
operación usa su propia conexión: un intento fallido queda registrado aunque la
petición termine en error y su transacción se revierta.
"""

from datetime import timedelta

from sqlalchemy import delete, func, insert, select

from app.core.database import engine
from app.models.login_attempt import LoginAttempt


class LoginAttemptLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)

    def is_blocked(self, key: str) -> bool:
        stmt = select(func.count()).where(LoginAttempt.key == key, LoginAttempt.created_at > func.now() - self.window)
        with engine.connect() as conn:
            return (conn.scalar(stmt) or 0) >= self.max_attempts

    def hit(self, key: str) -> None:
        with engine.begin() as conn:
            conn.execute(delete(LoginAttempt).where(LoginAttempt.created_at <= func.now() - self.window))
            conn.execute(insert(LoginAttempt).values(key=key))

    def reset(self, key: str) -> None:
        with engine.begin() as conn:
            conn.execute(delete(LoginAttempt).where(LoginAttempt.key == key))
