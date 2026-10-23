"""Errores de validación en español y sin repetir lo que se envió.

FastAPI responde por defecto con los mensajes de Pydantic en inglés ("String should have at least
10 characters") y con el valor recibido, que puede ser una contraseña. Acá se arma un mensaje
claro por campo ("Contraseña: tiene que tener al menos 10 caracteres") y se descarta el valor.
"""

from typing import Any

FIELD_LABELS = {
    "email": "Email", "password": "Contraseña", "current_password": "Contraseña actual",
    "new_password": "Nueva contraseña", "name": "Nombre", "currency": "Moneda",
    "monthly_budget": "Presupuesto mensual", "daily_limit": "Límite diario", "amount": "Monto",
    "date": "Fecha", "description": "Descripción", "method": "Método", "category_id": "Categoría",
    "account_id": "Cuenta", "kind": "Tipo", "supplier": "Proveedor", "ruc": "RUC", "number": "Número",
    "stamp": "Timbrado", "cdc": "CDC", "issue_date": "Fecha de emisión", "due_date": "Vencimiento",
    "total": "Total", "iva10": "IVA 10 %", "iva5": "IVA 5 %", "exempt": "Exentas", "notes": "Notas",
    "file_key": "Archivo", "paid_on": "Fecha del pago", "month": "Mes", "day_of_month": "Día del mes",
    "start_month": "Mes de inicio", "end_month": "Último mes", "color": "Color", "type": "Tipo de cuenta",
    "opening_balance": "Saldo", "closing_day": "Día de cierre", "due_day": "Día de vencimiento",
    "credit_limit": "Límite de crédito", "from_account_id": "Cuenta de origen", "to_account_id": "Cuenta de destino",
    "pattern": "Texto de la regla", "match": "Tipo de regla", "notify_hour": "Hora del aviso",
    "notify_days_before": "Días de anticipación", "endpoint": "Dispositivo", "items": "Movimientos",
    "year": "Año", "q": "Búsqueda", "limit": "Cantidad", "offset": "Desde", "start": "Desde", "end": "Hasta",
    "file": "Archivo", "mapping": "Columnas", "label": "Nombre del dispositivo",
}  # fmt: skip


def _text(err: dict[str, Any], field: str) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    if kind == "missing":
        return "es obligatorio"
    if kind == "string_too_short":
        n = ctx.get("min_length", 1)
        return "no puede quedar vacío" if n == 1 else f"tiene que tener al menos {n} caracteres"
    if kind == "string_too_long":
        return f"puede tener como máximo {ctx.get('max_length')} caracteres"
    if kind == "value_error":
        if "email" in field:
            return "no es un email válido (ejemplo: nombre@gmail.com)"
        # Nuestros validadores ya escriben el mensaje en español ("Mes inválido, usar AAAA-MM").
        message = str(ctx.get("error") or err.get("msg", ""))
        return message.removeprefix("Value error, ") or "no es válido"
    if kind in ("greater_than", "greater_than_equal"):
        limit = ctx.get("gt", ctx.get("ge"))
        return "tiene que ser mayor a cero" if str(limit) in ("0", "0.0") else f"tiene que ser al menos {limit}"
    if kind in ("less_than", "less_than_equal"):
        return f"puede ser como máximo {ctx.get('lt', ctx.get('le'))}"
    if kind == "decimal_max_places":
        return f"admite hasta {ctx.get('decimal_places')} decimales"
    if kind in ("decimal_max_digits", "decimal_whole_digits"):
        return "es un número demasiado grande"
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return "tiene que ser un número entero"
    if kind in ("decimal_parsing", "decimal_type", "float_parsing", "finite_number"):
        return "tiene que ser un número"
    if kind.startswith("date") or kind.startswith("datetime"):
        return "no es una fecha válida (usá AAAA-MM-DD)"
    if kind in ("enum", "literal_error"):
        return "no es una opción válida"
    if kind == "string_pattern_mismatch":
        return "tiene un formato inválido"
    if kind in ("bool_parsing", "bool_type"):
        return "tiene que ser sí o no"
    if kind in ("too_short", "too_long"):
        # Las contraseñas (SecretStr) usan estos códigos en lugar de string_too_short/long.
        if ctx.get("field_type") == "Value" or "password" in field:
            if kind == "too_short":
                return f"tiene que tener al menos {ctx.get('min_length')} caracteres"
            return f"puede tener como máximo {ctx.get('max_length')} caracteres"
        return "tiene una cantidad de elementos no permitida"
    return "no es válido"


def spanish_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for err in errors:
        loc = [p for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        field = next((str(p) for p in reversed(loc) if isinstance(p, str)), "")
        if err.get("type") in ("json_invalid", "model_attributes_type", "dict_type") or not field:
            msg = "Los datos enviados no son válidos"
        else:
            msg = f"{FIELD_LABELS.get(field, field.replace('_', ' ').capitalize())}: {_text(err, field)}"
        out.append({"loc": list(err.get("loc", ())), "type": err.get("type"), "msg": msg})
    return out
