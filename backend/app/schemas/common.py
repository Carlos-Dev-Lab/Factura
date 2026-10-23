import datetime as dt
import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    SecretStr,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

# Ids de la base (columnas integer de PostgreSQL). Uno más grande no existe y, sin este tope,
# PostgreSQL responde "integer out of range" y la API devolvía un error 500.
MAX_DB_ID = 2_147_483_647
RefId = Annotated[int, Field(ge=1, le=MAX_DB_ID)]

# Montos: Decimal exacto en el servidor, número en JSON para el cliente.
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]
PositiveMoney = Annotated[
    Decimal,
    Field(gt=0, max_digits=14, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]
# Saldos: pueden ser negativos (deuda de una tarjeta, cuenta en rojo).
SignedMoney = Annotated[
    Decimal,
    Field(max_digits=14, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]

# Montos de las respuestas: sin tope de dígitos. Cada monto cargado tiene tope, pero la suma de
# muchos puede pasarlo, y eso no debe romper un informe.
Amount = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

# [0-9] y no \d: \d también acepta dígitos de otros alfabetos ("٢٠٢٦"), que después rompían el
# nombre del archivo descargado. fullmatch: con match y $, "2026-10\n" también pasaba.
_MONTH_RE = re.compile(r"([0-9]{4})-(0[1-9]|1[0-2])")
MIN_YEAR, MAX_YEAR = 1900, 2999


def _check_month(v: str) -> str:
    m = _MONTH_RE.fullmatch(v)
    # El rango de años evita fechas imposibles (año 0) al calcular el mes anterior.
    if not m or not MIN_YEAR <= int(m.group(1)) <= MAX_YEAR:
        raise ValueError("Mes inválido, usar AAAA-MM")
    return v


def _check_date(v: dt.date) -> dt.date:
    if not MIN_YEAR <= v.year <= MAX_YEAR:
        raise ValueError(f"La fecha debe estar entre los años {MIN_YEAR} y {MAX_YEAR}")
    return v


Month = Annotated[str, AfterValidator(_check_month)]
# Fechas que carga el usuario: el mismo rango que los meses (un "0001-01-01" tipeado por error
# quedaba guardado y fuera de todos los informes).
Date = Annotated[dt.date, AfterValidator(_check_date)]
# (Los `pattern=` de Pydantic usan el motor de Rust, donde $ sí es el final exacto del texto.)
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]

# Caracteres de control invisibles (salvo tabulación y saltos de línea). PostgreSQL no acepta el
# carácter nulo y los demás solo llegan pegando texto de otro lado: se quitan en silencio.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str) -> str:
    return _CONTROL_CHARS.sub("", value)


class InputModel(BaseModel):
    """Base de los datos que envía el cliente: limpia los textos antes de validarlos."""

    @field_validator("*", mode="before")
    @classmethod
    def _clean_strings(cls, value: Any, info: ValidationInfo) -> Any:
        field = cls.model_fields.get(info.field_name or "")
        # Las contraseñas no se tocan: se comparan tal cual se escribieron.
        if isinstance(value, str) and not (field and field.annotation in (SecretStr, SecretStr | None)):
            return clean_text(value)
        return value


# Nombres obligatorios: se recortan los espacios y no pueden quedar vacíos ("   " se rechaza).
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
PaymentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryRef(ORMModel):
    id: int
    name: str
    color: str


class AccountRef(ORMModel):
    id: int
    name: str
    color: str
    type: str
