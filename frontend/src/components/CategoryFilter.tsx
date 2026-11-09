import type { TransactionKind } from '../api/types';
import { CategorySelect } from './fields';

export function CategoryFilter({ categoryId, onChange, kind }: {
  categoryId?: number;
  onChange: (id: number | null) => void;
  kind?: TransactionKind;
}) {
  return (
    <div className="category-filter">
      <CategorySelect kind={kind} value={categoryId ?? null} onChange={onChange} emptyLabel="Todas las categorías" />
      {categoryId !== undefined && (
        <button type="button" className="btn small" onClick={() => onChange(null)}>Quitar filtro</button>
      )}
    </div>
  );
}
