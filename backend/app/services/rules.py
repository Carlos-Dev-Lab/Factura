"""Categorización automática: reglas por RUC o por texto, aprendidas o creadas a mano.

Cada vez que el usuario elige una categoría para un proveedor (RUC) o para una
descripción, se recuerda. La próxima vez se sugiere sola, en facturas, en el
registro rápido y al importar extractos.
"""

import re
import unicodedata

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Category, CategoryKind, CategoryRule, User
from app.schemas.support import RuleIn, RuleMatch, SuggestionOut
from app.services import categories
from app.services.invoice_parser import guess_category

MAX_LEARNED_RULES = 1000
MIN_TEXT, MAX_TEXT = 3, 60
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con espacios simples: "Biggie  Señor" -> "biggie senor"."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _SPACES.sub(" ", plain).strip().lower()


def normalize_ruc(ruc: str) -> str:
    return re.sub(r"[^\d-]", "", ruc)


def list_rules(db: Session, user: User) -> list[CategoryRule]:
    stmt = select(CategoryRule).where(CategoryRule.user_id == user.id)
    return list(db.scalars(stmt.order_by(CategoryRule.learned, CategoryRule.match, CategoryRule.pattern)))


def create(db: Session, user: User, data: RuleIn) -> CategoryRule:
    category = categories.get_owned(db, user, data.category_id)
    pattern = normalize_ruc(data.pattern) if data.match == RuleMatch.ruc else normalize(data.pattern)
    rule = _upsert(db, user, data.match, pattern, category.id, learned=False)
    if rule is None:  # pragma: no cover - el patrón normalizado quedó vacío
        raise NotFoundError("Regla")
    return rule


def delete_rule(db: Session, user: User, rule_id: int) -> None:
    rule = db.get(CategoryRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise NotFoundError("Regla")
    db.delete(rule)


def _upsert(
    db: Session, user: User, match: RuleMatch, pattern: str, category_id: int, *, learned: bool
) -> CategoryRule | None:
    if not pattern:
        return None
    stmt = insert(CategoryRule).values(
        user_id=user.id, match=match.value, pattern=pattern, category_id=category_id, learned=learned
    )
    # Lo último que eligió el usuario manda. Una regla creada a mano no vuelve a ser "aprendida".
    stmt = stmt.on_conflict_do_update(
        constraint="uq_rule_user_match_pattern",
        set_={
            "category_id": category_id,
            "updated_at": func.now(),
            "learned": CategoryRule.learned & learned,
        },
    ).returning(CategoryRule.id)
    rule_id = db.scalar(stmt)
    db.flush()
    return db.get(CategoryRule, rule_id, populate_existing=True)


def learn_from_invoice(db: Session, user: User, ruc: str, category_id: int | None) -> None:
    ruc = normalize_ruc(ruc)
    if category_id is None or len(ruc) < 5:
        return
    _upsert(db, user, RuleMatch.ruc, ruc, category_id, learned=True)
    _trim(db, user)


def learn_from_text(db: Session, user: User, text: str, category_id: int | None) -> None:
    pattern = normalize(text)
    if category_id is None or not MIN_TEXT <= len(pattern) <= MAX_TEXT:
        return
    _upsert(db, user, RuleMatch.contains, pattern, category_id, learned=True)
    _trim(db, user)


def _trim(db: Session, user: User) -> None:
    """Mantiene acotada la cantidad de reglas aprendidas (borra las más viejas)."""
    learned = select(CategoryRule.id).where(CategoryRule.user_id == user.id, CategoryRule.learned.is_(True))
    count = db.scalar(select(func.count()).select_from(learned.subquery())) or 0
    if count <= MAX_LEARNED_RULES:
        return
    oldest = learned.order_by(CategoryRule.updated_at).limit(count - MAX_LEARNED_RULES)
    db.execute(delete(CategoryRule).where(CategoryRule.id.in_(oldest)))


class Suggester:
    """Sugiere categorías para muchos textos con una sola consulta (útil al importar)."""

    def __init__(self, db: Session, user: User) -> None:
        stmt = (
            select(CategoryRule.match, CategoryRule.pattern, CategoryRule.learned, Category.id, Category.kind)
            .join(Category, Category.id == CategoryRule.category_id)
            .where(CategoryRule.user_id == user.id)
        )
        self._ruc: dict[str, tuple[int, CategoryKind]] = {}
        self._contains: list[tuple[str, bool, int, CategoryKind]] = []
        for match, pattern, learned, cat_id, kind in db.execute(stmt):
            if match == RuleMatch.ruc:
                self._ruc[pattern] = (cat_id, kind)
            else:
                self._contains.append((pattern, learned, cat_id, kind))
        # Las reglas manuales primero; entre iguales, la más específica (más larga).
        self._contains.sort(key=lambda r: (r[1], -len(r[0])))
        self._by_name = {(c.name, c.kind): c.id for c in categories.list_categories(db, user)}

    def suggest(self, kind: CategoryKind, *, text: str = "", ruc: str = "") -> SuggestionOut:
        if ruc and (hit := self._ruc.get(normalize_ruc(ruc))) and hit[1] == kind:
            return SuggestionOut(category_id=hit[0], source="ruc")
        norm = normalize(text)
        if norm:
            for pattern, learned, cat_id, cat_kind in self._contains:
                if cat_kind == kind and pattern in norm:
                    return SuggestionOut(category_id=cat_id, source="historial" if learned else "regla")
            name = guess_category(text.upper()) if kind == CategoryKind.expense else None
            if name and (cat_id := self._by_name.get((name, kind))):
                return SuggestionOut(category_id=cat_id, source="sugerencia")
        return SuggestionOut(category_id=None, source=None)


def suggest(db: Session, user: User, kind: CategoryKind, *, text: str = "", ruc: str = "") -> SuggestionOut:
    return Suggester(db, user).suggest(kind, text=text, ruc=ruc)
