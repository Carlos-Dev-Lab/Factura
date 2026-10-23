from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, CurrentUser, PathId, verify_csrf
from app.models import Category, CategoryKind, CategoryRule
from app.schemas.category import CategoryIn, CategoryOut, CategoryUpdate
from app.schemas.support import DeletedOut, RuleIn, RuleOut, SuggestionOut
from app.services import categories, rules

router = APIRouter(prefix="/categories", tags=["categorías"], dependencies=[Depends(verify_csrf)])


@router.get("", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DB) -> list[Category]:
    return categories.list_categories(db, user)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryIn, user: CurrentUser, db: DB) -> Category:
    return categories.create(db, user, data)


@router.get("/suggest", response_model=SuggestionOut)
def suggest_category(
    user: CurrentUser,
    db: DB,
    kind: CategoryKind = CategoryKind.expense,
    text: str = Query("", max_length=200),
    ruc: str = Query("", max_length=20),
) -> SuggestionOut:
    """Categoría sugerida para un texto o un RUC, según lo que el usuario eligió antes."""
    return rules.suggest(db, user, kind, text=text, ruc=ruc)


@router.get("/rules", response_model=list[RuleOut])
def list_rules(user: CurrentUser, db: DB) -> list[CategoryRule]:
    return rules.list_rules(db, user)


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(data: RuleIn, user: CurrentUser, db: DB) -> CategoryRule:
    return rules.create(db, user, data)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: PathId, user: CurrentUser, db: DB) -> None:
    rules.delete_rule(db, user, rule_id)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: PathId, data: CategoryUpdate, user: CurrentUser, db: DB) -> Category:
    return categories.update(db, user, category_id, data)


@router.delete("/{category_id}", response_model=DeletedOut)
def delete_category(category_id: PathId, user: CurrentUser, db: DB) -> DeletedOut:
    return DeletedOut(trash_id=categories.delete(db, user, category_id))
