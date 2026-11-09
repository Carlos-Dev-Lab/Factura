import { Link } from 'react-router-dom';

import { CategoryFilter } from '../components/CategoryFilter';
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
import { useActiveAccounts, useSummary, useTransactions, useUser } from '../hooks/queries';
import { useCategoryFilter } from '../hooks/useCategoryFilter';
import { formatMoney, monthBounds, monthLabel, monthOf, todayIso } from '../lib/format';

const RECENT = 8;

export function DashboardPage() {
  const { month } = useMonth();
  const { categoryId, selectCategory } = useCategoryFilter();
  return (
    <div className="stack">
      {month === monthOf(todayIso()) && <AlertsStrip />}
      <div className="toolbar">
        <CategoryFilter categoryId={categoryId} onChange={selectCategory} />
      </div>
      <DashboardContent categoryId={categoryId} />
    </div>
  );
}

function DashboardContent({ categoryId }: { categoryId?: number }) {
  const { month } = useMonth();
  const user = useUser();
  const summary = useSummary(month, categoryId);
  const recent = useTransactions({ ...monthBounds(month), limit: RECENT, category_id: categoryId });
  const { data: accounts } = useActiveAccounts();
  if (!summary.data) return <Loading error={summary.error} />;
  const s = summary.data;
  const money = (v: number) => formatMoney(v, user.currency);
  const used = s.budget_used_pct ?? 0;
  const meter = used >= 100 ? 'bad' : used >= 80 ? 'warn' : '';
  const change = s.expense_change_pct;
  const todayPct = s.daily_limit ? Math.round((s.today_expense / s.daily_limit) * 100) : null;
  const isCurrent = month === monthOf(todayIso());
  const available = accounts?.reduce((total, account) => account.type === 'card' ? total : total + account.balance, 0);

  return (
    <div className="stack">
      <section className="grid kpis" aria-label="Resumen del mes">
        <div className="hero">
          <div className="soft">
            Hola{user.name ? `, ${user.name}` : ''} · Disponible hoy
            {categoryId !== undefined && ' · Todas las cuentas'}
          </div>
          <div className={`num big ${available !== undefined && available < 0 ? 'neg' : ''}`}>
            {available === undefined ? '—' : money(available)}
          </div>
          <div className="soft">
            Resultado de {monthLabel(month).toLowerCase()} · <b>{money(s.balance)}</b>
          </div>
          <div className="pills">
            {change !== null && (
              <span className={`pill ${change > 0 ? 'coral' : 'mint'}`}>
                {change > 0 ? '▲ ' : change < 0 ? '▼ ' : ''}
                {Math.abs(change).toLocaleString('es-PY')} % en gastos · {isCurrent ? 'mes en curso vs. mes anterior completo' : 'vs. mes anterior completo'}
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
          label="Ingresos del mes"
          value={money(s.income)}
          hint={`Mes anterior: ${money(s.previous_income)}`}
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
          hint={categoryId !== undefined ? 'Categoría seleccionada' : todayPct === null ? 'Sin límite diario' : `${todayPct}% del límite diario`}
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
          <DailyBars daily={s.daily} limit={s.daily_limit} categoryId={categoryId} />
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
            <Link to={categoryId === undefined ? '/gastos' : `/gastos?categoria=${categoryId}`} className="link">
              Ver todos
            </Link>
          </div>
          <TransactionList items={recent.data?.items ?? []} emptyText={categoryId === undefined
            ? 'Registrá tu primer movimiento con el botón “+”.'
            : 'No hay movimientos de esta categoría en el mes.'} />
        </div>
        <div className="card">
          <div className="card-head">
            <h2>Próximos pagos y cobros</h2>
            <Link to={categoryId === undefined ? '/calendario' : `/calendario?categoria=${categoryId}`} className="link">
              Calendario
            </Link>
          </div>
          <DueList items={s.upcoming.slice(0, 6)} emptyText="No hay pagos pendientes." />
        </div>
      </section>
    </div>
  );
}
