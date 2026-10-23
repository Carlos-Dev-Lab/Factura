from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import fetch
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import Category, CategoryKind, User
from app.schemas.category import CategoryIn, CategoryUpdate

DEFAULT_CATEGORIES: list[tuple[str, str, CategoryKind]] = [
    ("Supermercado", "#3EE6B0", CategoryKind.expense),
    ("Servicios", "#8B7BFF", CategoryKind.expense),
    ("Transporte", "#FFC24D", CategoryKind.expense),
    ("Comidas", "#FF8A5B", CategoryKind.expense),
    ("Salud", "#FF6B9A", CategoryKind.expense),
    ("Hogar", "#5AB8FF", CategoryKind.expense),
    ("Educación", "#C38BFF", CategoryKind.expense),
    ("Ocio", "#4DD4E6", CategoryKind.expense),
    ("Otros", "#A3ADC8", CategoryKind.expense),
    ("Sueldo", "#3EE6B0", CategoryKind.income),
    ("Freelance", "#8B7BFF", CategoryKind.income),
    ("Otros ingresos", "#5AB8FF", CategoryKind.income),
]


def seed_defaults(db: Session, user: User) -> None:
    db.add_all(Category(user_id=user.id, name=n, color=c, kind=k) for n, c, k in DEFAULT_CATEGORIES)


def list_categories(db: Session, user: User) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.user_id == user.id).order_by(Category.kind, Category.id)))


def get_owned(db: Session, user: User, category_id: int, *, lock: bool = False) -> Category:
    cat = fetch(db, Category, category_id, lock=lock)
    if not cat or cat.user_id != user.id:
        raise NotFoundError("Categoría")
    return cat


def resolve(db: Session, user: User, category_id: int | None, kind: CategoryKind) -> int | None:
    """Valida que la categoría exista, sea del usuario y del tipo correcto."""
    if category_id is None:
        return None
    cat = get_owned(db, user, category_id)
    if cat.kind != kind:
        raise ValidationError("La categoría no corresponde al tipo de movimiento")
    return cat.id


def find_by_name(db: Session, user: User, name: str, kind: CategoryKind) -> Category | None:
    return db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name, Category.kind == kind))


def _check_name(db: Session, user: User, name: str, kind: CategoryKind, exclude_id: int | None = None) -> None:
    """Sin repetidas aunque cambien mayúsculas: "Mascotas" y "mascotas" serían la misma para la persona."""
    stmt = select(Category.id).where(
        Category.user_id == user.id, Category.kind == kind, func.lower(Category.name) == name.strip().lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    if db.scalar(stmt):
        raise ConflictError("Ya existe una categoría con ese nombre")


def _flush_unique(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Ya existe una categoría con ese nombre") from exc


def _budget(kind: CategoryKind, value: Decimal | None) -> Decimal | None:
    if not value:
        return None
    if kind != CategoryKind.expense:
        raise ValidationError("Solo las categorías de gasto tienen presupuesto")
    return value


def create(db: Session, user: User, data: CategoryIn) -> Category:
    _check_name(db, user, data.name, data.kind)
    cat = Category(
        user_id=user.id,
        name=data.name.strip(),
        color=data.color,
        kind=data.kind,
        monthly_budget=_budget(data.kind, data.monthly_budget),
    )
    db.add(cat)
    _flush_unique(db)
    return cat


def update(db: Session, user: User, category_id: int, data: CategoryUpdate) -> Category:
    cat = get_owned(db, user, category_id, lock=True)
    if data.name is not None:
        _check_name(db, user, data.name, cat.kind, exclude_id=cat.id)
        cat.name = data.name.strip()
    if data.color is not None:
        cat.color = data.color
    if "monthly_budget" in data.model_fields_set:
        cat.monthly_budget = _budget(cat.kind, data.monthly_budget)
    _flush_unique(db)
    return cat


def delete(db: Session, user: User, category_id: int) -> int:
    """Borra la categoría (queda en la papelera) y devuelve el id del elemento de la papelera."""
    from app.services import trash  # import local: trash depende de los modelos, no de este módulo

    cat = get_owned(db, user, category_id, lock=True)
    item = trash.trash_category(db, user, cat)
    db.delete(cat)
    db.flush()
    return item.id
