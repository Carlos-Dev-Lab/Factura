import { Link } from 'react-router-dom';

import type { BudgetStatus } from '../../api/types';
import { useUser } from '../../hooks/queries';
import { formatMoney } from '../../lib/format';

const METER = { ok: '', warn: 'warn', over: 'bad' } as const;

export function BudgetsCard({ budgets }: { budgets: BudgetStatus[] }) {
  const { currency } = useUser();
  return (
    <section className="card" aria-label="Presupuesto por categoría">
      <div className="card-head">
        <h2>Presupuestos</h2>
        <Link to="/ajustes?seccion=perfil" className="link">
          Editar
        </Link>
      </div>
      {budgets.length ? (
        <ul className="budget-list">
          {budgets.map((b) => (
            <li key={b.category_id}>
              <div className="row-between">
                <span className="budget-name">
                  <i style={{ background: b.color }} aria-hidden="true" />
                  {b.name}
                </span>
                <span className={`small ${b.state === 'over' ? 'neg' : b.state === 'warn' ? 'amber' : 'muted'}`}>
                  {formatMoney(b.spent, currency, { short: true })} de {formatMoney(b.budget, currency, { short: true })}
                </span>
              </div>
              <div
                className={`meter thin ${METER[b.state]}`}
                role="meter"
                aria-valuenow={Math.round(b.pct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${b.name}: ${Math.round(b.pct)}% del presupuesto`}
              >
                <div style={{ width: `${Math.min(100, b.pct)}%` }} />
              </div>
              {b.state === 'over' && (
                <span className="hint neg">Te pasaste por {formatMoney(b.spent - b.budget, currency)}</span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">
          Poné un tope a las categorías que más te importan (comidas, salidas, compras) y el panel te avisa al llegar
          al 80 %. <Link to="/ajustes?seccion=perfil">Definir presupuestos</Link>
        </div>
      )}
    </section>
  );
}
