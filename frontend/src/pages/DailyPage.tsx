import { useDeferredValue, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { reportsApi, transactionsApi } from '../api/endpoints';
import type { PaymentMethod, TransactionKind } from '../api/types';
import { AccountSelect, Field, MoneyInput } from '../components/fields';
import { Icon } from '../components/Icon';
import { Loading } from '../components/Loading';
import { useDialogs } from '../context/DialogsContext';
import { useMonth } from '../context/MonthContext';
import { useToast } from '../context/ToastContext';
import { ImportDialog } from '../features/imports/ImportDialog';
import { TransactionList } from '../features/transactions/TransactionList';
import { useActiveAccounts, useCategories, useFinancialMutation, useTransactions, useUser } from '../hooks/queries';
import { SUGGESTION_SOURCE, useCategorySuggestion } from '../hooks/useSuggestion';
import {
  formatDate,
  formatMoney,
  isIsoDate,
  isoDate,
  monthBounds,
  monthOf,
  parseIso,
  PAYMENT_METHODS,
} from '../lib/format';

const STRIP_DAYS = 7;
const MONTH_LIST_LIMIT = 200;
// Máximo que devuelve la API: el total del día se calcula con todos sus movimientos.
const DAY_LIST_LIMIT = 500;

function weekAround(iso: string): string[] {
  const center = parseIso(iso);
  return Array.from({ length: STRIP_DAYS }, (_, i) => {
    const d = new Date(center);
    d.setDate(center.getDate() + i - Math.floor(STRIP_DAYS / 2));
    return isoDate(d);
  });
}

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

function MonthList({ month }: { month: string }) {
  const { currency } = useUser();
  const { openTransaction } = useDialogs();
  const { defaultDay } = useMonth();
  const { data: accounts = [] } = useActiveAccounts();
  const [params, setParams] = useSearchParams();
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
  });

  const setAccount = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('cuenta', String(id));
    else next.delete('cuenta');
    setParams(next, { replace: true });
  };

  return (
    <section className="card">
      <div className="card-head">
        <h2>Todo el mes</h2>
        <div className="row-actions">
          <button className="btn small" onClick={() => openTransaction({ kind: 'income', date: defaultDay })}>
            + Ingreso
          </button>
          <button className="btn small" onClick={() => setImporting(true)}>
            <Icon name="upload" size={16} /> Importar extracto
          </button>
          <a className="btn small" href={reportsApi.exportUrl(month)}>
            Exportar CSV
          </a>
        </div>
      </div>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Tipo">
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
      </div>
      {list.data ? (
        <>
          <div className="list-totals">
            <span>
              {list.data.total} movimientos · Gastos <b className="neg">{formatMoney(list.data.expense_total, currency)}</b>
            </span>
            <span>
              Ingresos <b className="pos">{formatMoney(list.data.income_total, currency)}</b>
            </span>
          </div>
          <TransactionList items={list.data.items} emptyText="No hay movimientos con estos filtros." />
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

export function DailyPage() {
  const { month, setMonth, defaultDay } = useMonth();
  const { currency, daily_limit: limit } = useUser();
  const [params, setParams] = useSearchParams();
  const requested = params.get('dia');
  // El día de la URL solo vale si es una fecha real del mes elegido; si no, se usa el día por defecto.
  const day = isIsoDate(requested) && monthOf(requested) === month ? requested : defaultDay;
  const selectDay = (d: string) => {
    if (monthOf(d) !== month) setMonth(monthOf(d));
    const next = new URLSearchParams(params);
    next.set('dia', d);
    setParams(next);
  };

  const strip = weekAround(day);
  const dayTx = useTransactions({ start: day, end: day, limit: DAY_LIST_LIMIT });
  const weekTx = useTransactions({ start: strip[0], end: strip.at(-1), limit: DAY_LIST_LIMIT });
  const daysWithData = new Set(weekTx.data?.items.map((t) => t.date));
  const spent = dayTx.data?.expense_total ?? 0;
  const pct = limit ? Math.round((spent / limit) * 100) : 0;
  const ring = pct >= 100 ? '#FF8A5B' : pct >= 80 ? '#FFC24D' : '#3EE6B0';
  const fill = Math.min(100, pct);

  return (
    <div className="stack">
      <div className="strip" role="group" aria-label="Elegir día">
        {strip.map((d) => (
          <button
            key={d}
            className={d === day ? 'on' : ''}
            aria-pressed={d === day}
            aria-label={formatDate(d, 'long')}
            onClick={() => selectDay(d)}
          >
            <small>{formatDate(d, 'weekday')}</small>
            <b>{parseIso(d).getDate()}</b>
            <i className={daysWithData.has(d) ? 'has' : ''} />
          </button>
        ))}
      </div>

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
                : 'Definí un límite diario en Ajustes'}
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
          <TransactionList items={dayTx.data.items} emptyText="Sin movimientos este día." />
        ) : (
          <Loading error={dayTx.error} />
        )}
      </section>

      <MonthList month={month} />
    </div>
  );
}
