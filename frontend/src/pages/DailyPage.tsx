import { useDeferredValue, useEffect, useState, type CSSProperties } from 'react';
import { useSearchParams } from 'react-router-dom';

import { reportsApi, transactionsApi } from '../api/endpoints';
import type { PaymentMethod, TransactionKind } from '../api/types';
import { CategoryFilter } from '../components/CategoryFilter';
import { AccountSelect, Field, MoneyInput } from '../components/fields';
import { Icon } from '../components/Icon';
import { Loading } from '../components/Loading';
import { useDialogs } from '../context/DialogsContext';
import { useMonth } from '../context/MonthContext';
import { useToast } from '../context/ToastContext';
import { ImportDialog } from '../features/imports/ImportDialog';
import { TransactionList } from '../features/transactions/TransactionList';
import { useActiveAccounts, useCategories, useFinancialMutation, useSummary, useTransactions, useUser, useYearlyExpenses, useYearReport } from '../hooks/queries';
import { useCategoryFilter } from '../hooks/useCategoryFilter';
import { SUGGESTION_SOURCE, useCategorySuggestion } from '../hooks/useSuggestion';
import {
  defaultDayForMonth,
  formatDate,
  formatMoney,
  isIsoDate,
  monthBounds,
  monthLabel,
  monthOf,
  parseIso,
  PAYMENT_METHODS,
} from '../lib/format';

const STRIP_DAYS = 7;
const MONTH_LIST_LIMIT = 200;
// Máximo que devuelve la API: el total del día se calcula con todos sus movimientos.
const DAY_LIST_LIMIT = 500;

function QuickAdd({ day }: { day: string }) {
  const { data: categories = [] } = useCategories();
  const { data: accounts = [] } = useActiveAccounts();
  const toast = useToast();
  const expenseCats = categories.filter((c) => c.kind === 'expense');
  const [amount, setAmount] = useState(0);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [description, setDescription] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [accountId, setAccountId] = useState<number | null>(null);
  const [formKey, setFormKey] = useState(0);
  const save = useFinancialMutation(transactionsApi.create, 'Gasto agregado');
  // Si el usuario no tocó una categoría, se usa la que eligió antes para algo parecido.
  const suggestion = useCategorySuggestion('expense', description, categoryId === null);

  useEffect(() => {
    if (accountId === null && accounts.length) setAccountId(accounts[0]!.id);
  }, [accounts, accountId]);

  const selected = categoryId ?? suggestion?.category_id ?? expenseCats[0]?.id ?? null;
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (amount <= 0) {
      toast('Ingresá un monto mayor a cero');
      return;
    }
    const name = expenseCats.find((c) => c.id === selected)?.name ?? '';
    save.mutate(
      {
        kind: 'expense',
        amount,
        date: day,
        category_id: selected,
        description: description.trim() || name,
        method,
        account_id: accountId,
      },
      {
        onSuccess: () => {
          setAmount(0);
          setDescription('');
          setCategoryId(null);
          setFormKey((k) => k + 1); // reinicia el campo de monto
        },
      },
    );
  };

  return (
    <form className="card form" onSubmit={submit}>
      <h2 className="card-title">Registro rápido</h2>
      <MoneyInput key={formKey} label="Monto" value={amount} onChange={setAmount} />
      <Field label="Descripción">
        <input
          maxLength={160}
          placeholder="Ej. almuerzo, Biggie, nafta"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <div className="chips" role="group" aria-label="Categoría">
        {expenseCats.map((c) => (
          <button
            type="button"
            key={c.id}
            className={c.id === selected ? 'on' : ''}
            aria-pressed={c.id === selected}
            style={c.id === selected ? { background: c.color } : undefined}
            onClick={() => setCategoryId(c.id)}
          >
            {c.name}
          </button>
        ))}
      </div>
      {categoryId === null && suggestion?.source && (
        <span className="hint">{SUGGESTION_SOURCE[suggestion.source]}</span>
      )}
      <div className="fgrid">
        <AccountSelect
          value={accountId}
          onChange={(id) => {
            setAccountId(id);
            if (accounts.find((a) => a.id === id)?.type === 'card') setMethod('credit');
          }}
        />
        <Field label="Método">
          <select value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <button className="btn coral block" disabled={save.isPending}>
        Agregar gasto
      </button>
    </form>
  );
}

function MonthList({ month, categoryId }: { month: string; categoryId?: number }) {
  const { currency } = useUser();
  const { openTransaction } = useDialogs();
  const { data: accounts = [] } = useActiveAccounts();
  const [params, setParams] = useSearchParams();
  const viewParam = params.get('vista');
  const view = viewParam === 'por-anio' ? 'por-anio' : viewParam === 'por-mes' || viewParam === 'totales' ? 'por-mes' : 'detalle';
  const accountParam = Number(params.get('cuenta')) || undefined;
  const [kind, setKind] = useState<TransactionKind | undefined>();
  const [search, setSearch] = useState('');
  const [importing, setImporting] = useState(false);
  const q = useDeferredValue(search.trim());
  const list = useTransactions({
    ...monthBounds(month),
    kind,
    q: q || undefined,
    limit: MONTH_LIST_LIMIT,
    account_id: accountParam,
    category_id: categoryId,
  });

  const setAccount = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('cuenta', String(id));
    else next.delete('cuenta');
    setParams(next, { replace: true });
  };
  const setView = (selected: typeof view) => {
    const next = new URLSearchParams(params);
    if (selected === 'detalle') next.delete('vista');
    else next.set('vista', selected);
    setParams(next);
  };
  const openMonth = (selected: string) => setParams({ dia: defaultDayForMonth(selected) });

  return (
    <section className="card">
      <div className="card-head">
        <h2>Movimientos del mes</h2>
        <div className="row-actions">
          <button className="btn small" onClick={() => openTransaction({ kind: 'income' })}>
            + Ingreso
          </button>
          <button className="btn small" onClick={() => setImporting(true)}>
            <Icon name="upload" size={16} /> Importar extracto
          </button>
          {view === 'detalle' && <a className="btn small" href={reportsApi.exportUrl(month, categoryId)}>Exportar CSV</a>}
        </div>
      </div>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Vista de movimientos">
          {([
            { value: 'detalle', label: 'Detalle', description: 'Detalle del mes' },
            { value: 'por-mes', label: 'Por mes', description: 'Total de gastos por mes' },
            { value: 'por-anio', label: 'Por año', description: 'Total de gastos por año' },
          ] as const).map(({ value, label, description }) => (
            <button
              type="button"
              key={value}
              className={view === value ? 'on' : ''}
              aria-label={description}
              aria-pressed={view === value}
              onClick={() => setView(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {view === 'detalle' && <><div className="seg" role="group" aria-label="Tipo">
          {[
            { v: undefined, l: 'Todos' },
            { v: 'expense' as const, l: 'Gastos' },
            { v: 'income' as const, l: 'Ingresos' },
          ].map((o) => (
            <button key={o.l} className={kind === o.v ? 'on' : ''} aria-pressed={kind === o.v} onClick={() => setKind(o.v)}>
              {o.l}
            </button>
          ))}
        </div>
        {accounts.length > 1 && (
          <label className="search compact-select">
            <Icon name="wallet" size={18} />
            <span className="sr">Filtrar por cuenta</span>
            <select value={accountParam ?? ''} onChange={(e) => setAccount(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Todas las cuentas</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="search">
          <Icon name="search" size={18} />
          <span className="sr">Buscar movimientos</span>
          <input
            type="search"
            placeholder="Descripción o categoría…"
            maxLength={80}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        </>}
      </div>
      {view !== 'detalle' ? (
        <ExpenseTotals
          key={month.slice(0, 4)}
          initialYear={Number(month.slice(0, 4))}
          categoryId={categoryId}
          byYear={view === 'por-anio'}
          showMonths={() => setView('por-mes')}
          openMonth={openMonth}
        />
      ) : list.data ? (
        <>
          <div className="list-totals">
            <span>
              {list.data.total} movimientos · Gastos <b className="neg">{formatMoney(list.data.expense_total, currency)}</b>
            </span>
            <span>
              Ingresos <b className="pos">{formatMoney(list.data.income_total, currency)}</b>
            </span>
          </div>
          <TransactionList items={list.data.items} emptyText="No hay movimientos con estos filtros." allowSchedule />
          {list.data.total > list.data.items.length && (
            <p className="muted small">
              Se muestran {list.data.items.length} de {list.data.total} movimientos. Usá la búsqueda o el filtro para
              ver el resto, o exportá el CSV.
            </p>
          )}
        </>
      ) : (
        <Loading error={list.error} />
      )}
      {importing && <ImportDialog accountId={accountParam ?? null} onClose={() => setImporting(false)} />}
    </section>
  );
}

function ExpensePeriod({ label, caption, amount, hasExpenses, onClick }: {
  label: string;
  caption: string;
  amount: string;
  hasExpenses: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button type="button" className="item expense-period" onClick={onClick}>
        <span className="ava" aria-hidden="true"><Icon name="calendar" size={20} /></span>
        <span className="body">
          <b>{label}</b>
          <small>{hasExpenses ? caption : 'Sin gastos'}</small>
        </span>
        <span className={`amt ${hasExpenses ? 'neg' : 'muted'}`}>{amount}</span>
        <span className="period-chevron" aria-hidden="true"><Icon name="right" size={16} /></span>
      </button>
    </li>
  );
}

function ExpenseTotals({ initialYear, categoryId, byYear, showMonths, openMonth }: {
  initialYear: number;
  categoryId?: number;
  byYear: boolean;
  showMonths: () => void;
  openMonth: (month: string) => void;
}) {
  const { currency } = useUser();
  const [year, setYear] = useState(initialYear);
  const yearly = useYearlyExpenses(categoryId);
  const monthly = useYearReport(year, categoryId);
  const years = [...new Set([year, initialYear, ...(yearly.data ?? []).map((row) => row.year)])].sort((a, b) => b - a);
  const money = (amount: number) => formatMoney(amount, currency);

  return (
    <>
      <div className="toolbar">
        <span className="muted small">{categoryId === undefined ? 'Gastos de todas las cuentas' : 'Gastos de la categoría seleccionada'}</span>
        {!byYear && years.length > 1 && <label className="search compact-select">
          <span className="sr">Año de los gastos</span>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {years.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>}
      </div>
      {byYear ? yearly.data ? (
        yearly.data.length ? <ul className="list" aria-label="Gastos por año">
          {yearly.data.map((row) => (
            <ExpensePeriod
              key={row.year}
              label={String(row.year)}
              caption="Gastos del año"
              amount={money(row.expense)}
              hasExpenses={row.expense > 0}
              onClick={() => { setYear(row.year); showMonths(); }}
            />
          ))}
        </ul> : <div className="empty">Todavía no hay gastos registrados.</div>
      ) : <Loading error={yearly.error} /> : monthly.data ? (
        <>
          <div className="list-totals">
            <span>Total de {year}</span>
            <b className="neg">{money(monthly.data.expense)}</b>
          </div>
          <ul className="list" aria-label="Gastos por mes">
            {monthly.data.months.map((row) => (
              <ExpensePeriod
                key={row.month}
                label={monthLabel(row.month)}
                caption="Gastos del mes"
                amount={money(row.expense)}
                hasExpenses={row.expense > 0}
                onClick={() => openMonth(row.month)}
              />
            ))}
          </ul>
        </>
      ) : <Loading error={monthly.error} />}
    </>
  );
}

export function DailyPage() {
  const { setMonth, defaultDay } = useMonth();
  const { currency, daily_limit } = useUser();
  const { category, categoryId, selectCategory } = useCategoryFilter();
  const limit = categoryId === undefined ? daily_limit : 0;
  const [params, setParams] = useSearchParams();
  const requested = params.get('dia');
  // Un enlace directo a un día también abre su mes al recargar.
  useEffect(() => {
    if (isIsoDate(requested)) setMonth(monthOf(requested));
  }, [requested, setMonth]);
  const day = isIsoDate(requested) ? requested : defaultDay;
  const month = monthOf(day);
  const selectDay = (d: string) => {
    if (d !== day) setParams({ dia: d });
  };

  const monthly = useSummary(month, categoryId);
  const [week, setWeek] = useState<{ day: string; start: number }>();
  const days = monthly.data?.daily.filter(({ expense, income }) => expense > 0 || income > 0) ?? [];
  const lastStart = Math.max(0, Math.floor((days.length - 1) / STRIP_DAYS) * STRIP_DAYS);
  const selectedIndex = days.findIndex(({ date }) => date === day);
  const defaultStart = Math.max(0, Math.floor(selectedIndex / STRIP_DAYS) * STRIP_DAYS);
  const start = week?.day === day ? Math.min(week.start, lastStart) : defaultStart;
  const visibleDays = days.slice(start, start + STRIP_DAYS);
  const moveWeek = (direction: number) => {
    setWeek({ day, start: Math.max(0, Math.min(lastStart, start + direction * STRIP_DAYS)) });
  };
  const dayTx = useTransactions({ start: day, end: day, limit: DAY_LIST_LIMIT, category_id: categoryId });
  const spent = dayTx.data?.expense_total ?? 0;
  const pct = limit ? Math.round((spent / limit) * 100) : 0;
  const ring = pct >= 100 ? '#FF8A5B' : pct >= 80 ? '#FFC24D' : '#3EE6B0';
  const fill = Math.min(100, pct);

  return (
    <div className="stack">
      <div className="toolbar"><CategoryFilter categoryId={categoryId} onChange={selectCategory} /></div>
      {monthly.data ? (
        <section className="expense-week" aria-label="Días con movimientos">
          <div className="expense-week-nav">
            <span className="muted" aria-live="polite">{monthLabel(month)}</span>
            {lastStart > 0 && (
              <div className="row-actions">
                <button type="button" className="btn small" aria-label="Días anteriores" disabled={start === 0} onClick={() => moveWeek(-1)}>‹</button>
                <button type="button" className="btn small" aria-label="Días siguientes" disabled={start >= lastStart} onClick={() => moveWeek(1)}>›</button>
              </div>
            )}
          </div>
          {visibleDays.length ? (
          <div className="strip" role="group" aria-label="Elegir día con movimientos"
            style={{ '--day-count': visibleDays.length } as CSSProperties}>
            {visibleDays.map(({ date: d, expense, income }) => {
              const selected = d === day;
              const activity = [
                expense > 0 && `gastos ${formatMoney(expense, currency)}`,
                income > 0 && `ingresos ${formatMoney(income, currency)}`,
              ].filter(Boolean).join(', ');
              return (
                <button
                  type="button"
                  key={d}
                  className={selected ? 'on' : ''}
                  aria-pressed={selected}
                  aria-label={`${formatDate(d, 'long')}, ${activity}`}
                  onClick={() => {
                    setWeek({ day: d, start });
                    selectDay(d);
                  }}
                >
                  <small>{formatDate(d, 'weekday')}</small>
                  <b>{parseIso(d).getDate()}</b>
                  <span className="day-markers" aria-hidden="true">
                    {expense > 0 && <i className="expense-mark" />}
                    {income > 0 && <i className="income-mark" />}
                  </span>
                </button>
              );
            })}
          </div>
          ) : <p className="muted">No hay días con movimientos en este mes.</p>}
        </section>
      ) : <Loading error={monthly.error} />}

      <div className="grid auto">
        <section className="hero ring-card">
          <div className="ring" style={{ background: `conic-gradient(${ring} 0 ${fill}%, #0E1630 ${fill}% 100%)` }}>
            <div className="hole">{limit ? `${pct}%` : '—'}</div>
          </div>
          <div className="ring-text">
            <span className="soft">Gastado el {formatDate(day, 'long').toLowerCase()}</span>
            <span className="num xl">{formatMoney(spent, currency)}</span>
            <span className="soft">
              {limit
                ? `Límite diario ${formatMoney(limit, currency)} · ${
                    spent > limit ? 'excedido' : `quedan ${formatMoney(limit - spent, currency)}`
                  }`
                : category?.name ?? 'Definí un límite diario en Ajustes'}
            </span>
          </div>
        </section>
        <QuickAdd day={day} />
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Movimientos · {formatDate(day)}</h2>
          <span className="muted">{dayTx.data?.total ?? 0} registros</span>
        </div>
        {dayTx.data ? (
          <TransactionList items={dayTx.data.items} emptyText="Sin movimientos este día." allowSchedule />
        ) : (
          <Loading error={dayTx.error} />
        )}
      </section>

      <MonthList key={day} month={month} categoryId={categoryId} />
    </div>
  );
}
