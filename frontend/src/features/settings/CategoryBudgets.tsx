import { useRef } from 'react';

import { categoriesApi } from '../../api/endpoints';
import type { Category } from '../../api/types';
import { MoneyInput } from '../../components/fields';
import { useCategories, useFinancialMutation, useSummary, useUser } from '../../hooks/queries';
import { formatMoney, monthOf, todayIso } from '../../lib/format';
import { SectionHeader } from './SectionHeader';

function BudgetRow({ category, spent }: { category: Category; spent: number }) {
  const { currency } = useUser();
  const save = useFinancialMutation(
    (value: number) => categoriesApi.update(category.id, { monthly_budget: value || null }),
    'Presupuesto guardado',
    ['categories'],
  );
  const budget = category.monthly_budget ?? 0;
  const pct = budget ? Math.round((spent / budget) * 100) : null;
  // Valor escrito: se guarda al salir del campo (un ref evita re-renderizar en cada tecla).
  const pending = useRef(budget);

  return (
    <li className="budget-row">
      <span className="budget-name">
        <i style={{ background: category.color }} aria-hidden="true" />
        {category.name}
      </span>
      <div
        className="budget-input"
        onBlur={() => {
          if (pending.current !== budget) save.mutate(pending.current);
        }}
      >
        <MoneyInput key={`${category.id}-${budget}`} label={`Tope mensual de ${category.name}`} value={budget} onChange={(v) => (pending.current = v)} />
      </div>
      <small className={pct !== null && pct >= 100 ? 'neg' : pct !== null && pct >= 80 ? 'amber' : 'muted'}>
        {pct === null ? 'Sin tope' : `Este mes: ${formatMoney(spent, currency, { short: true })} (${pct}%)`}
      </small>
    </li>
  );
}

/** Tope de gasto por categoría: el panel muestra el avance y avisa al 80 % y al 100 %. */
export function CategoryBudgets() {
  const { data: categories = [] } = useCategories();
  const summary = useSummary(monthOf(todayIso()));
  const spent = new Map(summary.data?.by_category.map((c) => [c.category_id, c.amount]));
  const expense = categories.filter((c) => c.kind === 'expense');

  return (
    <section className="card">
      <SectionHeader
        title="Presupuesto por categoría"
        description="Poné un tope a las categorías que querés controlar. Dejalo vacío para no limitarla. Se guarda al salir del campo."
      />
      <ul className="budget-rows">
        {expense.map((c) => (
          <BudgetRow key={c.id} category={c} spent={spent.get(c.id) ?? 0} />
        ))}
      </ul>
    </section>
  );
}
