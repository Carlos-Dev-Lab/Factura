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
        <h2>{closed ? 'Cómo cerró el mes' : '¿Cómo cerrás el mes?'}</h2>
        {!closed && <span className="muted">{p.days_left === 1 ? 'Queda 1 día' : `Quedan ${p.days_left} días`}</span>}
      </div>
      <div className={`num big-figure ${negative ? 'neg' : 'pos'}`}>{money(p.projected_balance)}</div>
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
            <dt>Pagos que faltan</dt>
            <dd className="neg">− {money(p.pending_expense)}</dd>
          </div>
        )}
      </dl>
      {!closed && (
        <div className={`allowance ${negative ? 'bad' : ''}`}>
          {negative ? (
            <span>Con lo que falta pagar, el mes cierra en rojo. Revisá gastos que puedas postergar.</span>
          ) : (
            <span>
              Podés gastar <b>{money(p.daily_allowance ?? 0)}</b> por día sin quedar en rojo.
              {p.budget_daily_allowance !== null &&
                (p.budget_daily_allowance > 0 ? (
                  <>
                    {' '}
                    Para respetar tu presupuesto: <b>{money(p.budget_daily_allowance)}</b> por día.
                  </>
                ) : (
                  <> Con lo que falta pagar ya usaste todo el presupuesto del mes.</>
                ))}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
