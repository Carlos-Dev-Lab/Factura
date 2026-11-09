import { useSearchParams } from 'react-router-dom';

import type { TransactionKind } from '../api/types';
import { useCategories } from './queries';

export function useCategoryFilter(kind?: TransactionKind) {
  const [params, setParams] = useSearchParams();
  const { data } = useCategories();
  const requested = Number(params.get('categoria'));
  const category = data?.find((item) => item.id === requested && (!kind || item.kind === kind));

  const selectCategory = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id === null) next.delete('categoria');
    else next.set('categoria', String(id));
    setParams(next, { replace: true });
  };

  return { category, categoryId: category?.id, selectCategory };
}
