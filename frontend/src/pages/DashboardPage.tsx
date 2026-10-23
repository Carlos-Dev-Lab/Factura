import { Link } from 'react-router-dom';

import { Loading } from '../components/Loading';
import { useMonth } from '../context/MonthContext';
import { AlertsStrip } from '../features/alerts/AlertsPanel';
import { AccountsCard } from '../features/dashboard/AccountsCard';
import { BudgetsCard } from '../features/dashboard/BudgetsCard';
import { CategoryDonut } from '../features/dashboard/CategoryDonut';
import { DailyBars } from '../features/dashboard/DailyBars';
import { KpiCard } from '../features/dashboard/KpiCard';
import { ProjectionCard } from '../features/dashboard/ProjectionCard';
import { DueList } from '../features/dues/DueList';
import { TransactionList } from '../features/transactions/TransactionList';
import { useSummary, useTransactions, useUser } from '../hooks/queries';
import { formatMoney, monthBounds, monthLabel, monthOf, todayIso } from '../lib/format';

const RECENT = 8;
const CHANGE_CAP = 999;

export function DashboardPage() {
  const { month } = useMonth();
  const user = useUser();
  const summary = useSummary(month);
  const recent = useTransactions({ ...monthBounds(month), limit: RECENT });
  if (!summary.data) return <Loading error={summary.error} />;
  const s = summary.data;
  const money = (v: number) => formatMoney(v, user.currency);
  const used = s.budget_used_pct ?? 0;
  const meter = used >= 100 ? 'bad' : used >= 80 ? 'warn' : '';
  const change = s.expense_change_pct;
  const todayPct = s.daily_limit ? Math.round((s.today_expense / s.daily_limit) * 100) : null;
  const isCurrent = month === monthOf(todayIso());

  return (
    <div className="stack">
      {isCurrent && <AlertsStrip />}
      <section className="grid kpis" aria-label="Resumen del mes">
        <div className="hero">
          <div className="soft">
            Hola{user.name ? `, ${user.name}` : ''} · saldo de {monthLabel(month).toLowerCase()}
          </div>
          <div className={`num big ${s.balance < 0 ? 'neg' : ''}`}>{money(s.balance)}</div>
          <div className="pills">
            {change !== null && (
              <span className={`pill ${change > 0 ? 'coral' : 'mint'}`}>
                {change > 0 ? '▲' : '▼'} {Math.min(Math.abs(change), CHANGE_CAP)}% gastos vs. mes anterior
              </span>
            )}
            {s.budget > 0 && (
              <span className="pill ghost">
                Presupuesto usado: {used.toLocaleString('es-PY', { maximumFractionDigits: 1 })} %
              </span>
            )}
          </div>
          {s.budget > 0 && (
            <div className={`meter ${meter}`}>
              <div style={{ width: `${Math.min(100, used)}%` }} />
            </div>
          )}
        </div>
        <KpiCard
          label="Ingresos"
          value={money(s.income)}
          hint={`${s.transaction_count} movimientos en el mes`}
          color="#3EE6B0"
          tone="pos"
        />
        <KpiCard
          label="Gastos"
          value={money(s.expense)}
          hint={`Mes anterior: ${formatMoney(s.previous_expense, user.currency, { short: true })}`}
          color="#FF8A5B"
          tone="neg"
        />
        <KpiCard
          label="Por pagar"
          value={money(s.due_total)}
          hint={s.overdue_count ? `${s.overdue_count} pago(s) vencido(s)` : 'Nada vencido'}
          color="#FFC24D"
        />
        <KpiCard
          label="Gastado hoy"
          value={money(s.today_expense)}
          hint={todayPct === null ? 'Sin límite diario' : `${todayPct}% del límite diario`}
          color="#8B7BFF"
        />
      </section>

      <section className="grid three">
        <ProjectionCard summary={s} />
        <BudgetsCard budgets={s.budgets} />
        <AccountsCard />
      </section>

      <section className="grid two">
        <div className="card">
          <div className="card-head">
            <h2>Gastos diarios</h2>
            <span className="muted">{monthLabel(month)}</span>
          </div>
          <DailyBars daily={s.daily} limit={s.daily_limit} />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Por categoría</h2>
          </div>
          <CategoryDonut data={s.by_category} />
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <div className="card-head">
            <h2>Movimientos del mes</h2>
            <Link to="/gastos" className="link">
              Ver todos
            </Link>
          </div>
          <TransactionList items={recent.data?.items ?? []} emptyText="Registrá tu primer movimiento con el botón “+”." />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Próximos pagos y cobros</h2>
            <Link to="/calendario" className="link">
              Calendario
            </Link>
          </div>
          <DueList items={s.upcoming.slice(0, 6)} emptyText="No hay pagos pendientes." />
        </div>
      </section>
    </div>
  );
}
