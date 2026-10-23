from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.schemas.common import InputModel, Money, ORMModel

# El largo máximo de un email (RFC 5321); la columna de la base admite 255.
Email = Annotated[EmailStr, Field(max_length=254)]


class RegisterIn(InputModel):
    email: Email
    password: SecretStr = Field(min_length=10, max_length=128)
    name: str = Field("", max_length=80)


class LoginIn(InputModel):
    email: Email
    password: SecretStr = Field(max_length=128)


class PasswordChangeIn(InputModel):
    # Opcional solo para la primera contraseña de una cuenta creada con Google.
    current_password: SecretStr | None = Field(None, max_length=128)
    new_password: SecretStr = Field(min_length=10, max_length=128)


class AuthConfigOut(BaseModel):
    registration_open: bool
    # Todavía no hay ninguna cuenta: la pantalla pide crear la del administrador.
    first_user: bool
    # Google configurado y utilizable desde la dirección con la que se entró (localhost o HTTPS).
    google_login: bool = False


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    currency: str
    monthly_budget: Money
    daily_limit: Money
    has_password: bool
    google_email: str | None


class GoogleLinkOut(BaseModel):
    url: str


class ProfileUpdate(InputModel):
    name: str | None = Field(None, max_length=80)
    currency: str | None = Field(None, pattern="^(PYG|USD|ARS|BRL|EUR)$")
    monthly_budget: Money | None = None
    daily_limit: Money | None = None
