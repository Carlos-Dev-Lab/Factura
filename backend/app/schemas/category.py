from app.models import CategoryKind
from app.schemas.common import CategoryName, HexColor, InputModel, Money, ORMModel


class CategoryIn(InputModel):
    name: CategoryName
    color: HexColor = "#A3ADC8"
    kind: CategoryKind = CategoryKind.expense
    monthly_budget: Money | None = None


class CategoryUpdate(InputModel):
    name: CategoryName | None = None
    color: HexColor | None = None
    # null o 0 quita el presupuesto.
    monthly_budget: Money | None = None


class CategoryOut(ORMModel):
    id: int
    name: str
    color: str
    kind: CategoryKind
    monthly_budget: Money | None
