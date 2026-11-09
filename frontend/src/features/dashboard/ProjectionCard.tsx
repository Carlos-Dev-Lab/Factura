import type { MonthSummary } from '../../api/types';
import { useUser } from '../../hooks/queries';
import { formatMoney } from '../../lib/format';

/** "¿Cómo cerrás el mes?": lo que ya pasó más lo que falta cobrar y pagar. */
export function ProjectionCard({ summary }: { summary: MonthSummary }) {
  const { currency } = useUser();
  const p = summary.projection;
  const money = (v: number) => formatMoney(v, currency);
  const closed = p.days_left === 0;
  const negative = p.projected_balance < 0;

  return (
    <section className="card projection" aria-label="Proyección del mes">
      <div className="card-head">
        <h2>{closed ? 'Resultado del mes' : 'Resultado proyectado del mes'}</h2>
        {!closed && <span className="muted">{p.days_left === 1 ? 'Queda 1 día' : `Quedan ${p.days_left} días`}</span>}
      </div>
      <div className={`num big-figure ${negative ? 'neg' : 'pos'}`}>{money(p.projected_balance)}</div>
      <p className="muted small">Ingresos menos gastos del período. El dinero que ya tenías figura en Disponible hoy.</p>
      <dl className="breakdown">
        <div>
          <dt>Ingresos registrados</dt>
          <dd className="pos">+ {money(summary.income)}</dd>
        </div>
        {p.pending_income > 0 && (
          <div>
            <dt>Cobros esperados</dt>
            <dd className="pos">+ {money(p.pending_income)}</dd>
          </div>
        )}
        <div>
          <dt>Gastos registrados</dt>
          <dd className="neg">− {money(summary.expense)}</dd>
        </div>
        {p.pending_expense > 0 && (
          <div>
            <dt>Gastos pendientes</dt>
            <dd className="neg">− {money(p.pending_expense)}</dd>
          </div>
        )}
      </dl>
      {p.card_payments > 0 && (
        <p className="muted small">Resúmenes de tarjeta por pagar · <b>{money(p.card_payments)}</b>. Su pago reduce el efectivo disponible.</p>
      )}
      {!closed && p.budget_daily_allowance !== null && (
        <div className="allowance">
          {p.budget_daily_allowance > 0
            ? <>Margen del presupuesto · <b>{money(p.budget_daily_allowance)}</b> por día.</>
            : 'Los gastos registrados y pendientes consumen el presupuesto del mes.'}
        </div>
      )}
    </section>
  );
}
