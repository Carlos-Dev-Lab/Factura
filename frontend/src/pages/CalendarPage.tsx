import { useEffect, useRef, useState } from 'react';

import type { CalendarDay, DueItem, DueState } from '../api/types';
import { Loading } from '../components/Loading';
import { useDialogs } from '../context/DialogsContext';
import { useMonth } from '../context/MonthContext';
import { dueKindLabel, dueStateLabel, PayButton } from '../features/dues/DueList';
import { useCalendar, useUser } from '../hooks/queries';
import { formatDate, formatMoney, parseIso, todayIso } from '../lib/format';

const WEEKDAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const STATE_COLOR: Record<DueState | 'income' | 'expected', string> = {
  pending: '#FFC24D',
  paid: '#3EE6B0',
  overdue: '#FF8A5B',
  income: '#8B7BFF',
  expected: '#B3A8FF',
};
const MAX_CHIPS = 2;

const dueColor = (d: DueItem) => (d.direction === 'in' && d.state !== 'paid' ? STATE_COLOR.expected : STATE_COLOR[d.state]);
const chipClass = (d: DueItem) => (d.direction === 'in' && d.state !== 'paid' ? 'expected' : d.state);

function buildCells(days: CalendarDay[]): (CalendarDay | null)[] {
  const first = days[0] ? parseIso(days[0].date) : new Date();
  const lead = (first.getDay() + 6) % 7; // semana empieza en lunes
  const cells: (CalendarDay | null)[] = [...Array<null>(lead).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  return cells;
}

function DayDetail({ day }: { day: CalendarDay }) {
  const { currency } = useUser();
  const { openScheduled, openTransaction } = useDialogs();
  return (
    <div className="hero day-panel">
      <div>
        <div className="soft">Día seleccionado</div>
        <div className="num title">{formatDate(day.date, 'long')}</div>
      </div>
      <ul className="list">
        {day.dues.length ? (
          day.dues.map((d: DueItem) => (
            <li key={`${d.kind}-${d.id}`} className="item inset">
              <span className="bar-mark" style={{ background: dueColor(d) }} />
              <span className="body">
                <b>{d.name}</b>
                <small>
                  {dueStateLabel(d)} · {d.detail ?? dueKindLabel(d)}
                </small>
              </span>
              <span className={`amt ${d.direction === 'in' ? 'pos' : ''}`}>
                {d.estimated && <span className="muted">≈ </span>}
                {formatMoney(d.amount, currency)}
              </span>
              <PayButton due={d} />
            </li>
          ))
        ) : (
          <li className="empty inset">Sin pagos este día.</li>
        )}
      </ul>
      {(day.expense > 0 || day.income > 0) && (
        <div className="soft">
          {day.expense > 0 && (
            <>
              Gastos: <b className="neg">{formatMoney(day.expense, currency)}</b>{' '}
            </>
          )}
          {day.income > 0 && (
            <>
              Ingresos: <b className="pos">{formatMoney(day.income, currency)}</b>
            </>
          )}
        </div>
      )}
      <div className="row-actions start">
        <button className="btn mint" onClick={() => openScheduled({ dayOfMonth: parseIso(day.date).getDate() })}>
          + Pago fijo
        </button>
        <button className="btn" onClick={() => openTransaction({ date: day.date })}>
          + Movimiento este día
        </button>
      </div>
    </div>
  );
}

export function CalendarPage() {
  const { month, defaultDay } = useMonth();
  const { currency } = useUser();
  const calendar = useCalendar(month);
  const [selected, setSelected] = useState(defaultDay);
  const panelRef = useRef<HTMLDivElement>(null);
  const today = todayIso();

  useEffect(() => setSelected(defaultDay), [defaultDay]);

  if (!calendar.data) return <Loading error={calendar.error} />;
  const days = calendar.data.days;
  const day = days.find((d) => d.date === selected) ?? days[0]!;
  const totals = { pending: 0, paid: 0, overdue: 0, expected: 0 };
  days.forEach((d) =>
    d.dues.forEach((due) => {
      if (due.direction === 'in') {
        if (due.state !== 'paid') totals.expected += due.amount;
      } else totals[due.state] += due.amount;
    }),
  );
  const income = days.reduce((s, d) => s + d.income, 0);

  const select = (date: string) => {
    setSelected(date);
    if (window.matchMedia('(max-width: 900px)').matches) panelRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      <div className="legend-row">
        {(['pending', 'paid', 'overdue'] as const).map((s) => (
          <span key={s}>
            <i style={{ background: STATE_COLOR[s] }} />
            {s === 'pending' ? 'Por pagar' : s === 'paid' ? 'Pagado' : 'Vencido'}
          </span>
        ))}
        <span>
          <i style={{ background: STATE_COLOR.expected }} />
          Cobro esperado
        </span>
        <span>
          <i style={{ background: STATE_COLOR.income }} />
          Ingresos
        </span>
      </div>
      <div className="cal-wrap">
        <section className="card cal" aria-label={`Calendario de ${month}`}>
          <div className="dow" aria-hidden="true">
            {WEEKDAYS.map((w) => (
              <span key={w}>{w}</span>
            ))}
          </div>
          <div className="days">
            {buildCells(days).map((d, i) =>
              d ? (
                <button
                  key={d.date}
                  className={`day ${d.date === today ? 'today' : ''} ${d.date === day.date ? 'sel' : ''}`}
                  aria-pressed={d.date === day.date}
                  aria-label={`${formatDate(d.date, 'long')}: ${d.dues.length} pagos`}
                  onClick={() => select(d.date)}
                >
                  <span className="n">
                    <span>{parseIso(d.date).getDate()}</span>
                    {d.expense > 0 && <em>{formatMoney(d.expense, currency, { short: true })}</em>}
                  </span>
                  {d.dues.slice(0, MAX_CHIPS).map((due) => (
                    <span key={`${due.kind}-${due.id}`} className={`ev ${chipClass(due)}`}>
                      {due.name}
                    </span>
                  ))}
                  {d.dues.length > MAX_CHIPS && <small className="muted">+{d.dues.length - MAX_CHIPS} más</small>}
                  {d.income > 0 && <span className="ev income">Ingreso</span>}
                  <span className="dots">
                    {d.dues.map((due) => (
                      <i key={`${due.kind}-${due.id}`} style={{ background: dueColor(due) }} />
                    ))}
                    {d.income > 0 && <i style={{ background: STATE_COLOR.income }} />}
                  </span>
                </button>
              ) : (
                <div key={`empty-${i}`} className="day out" aria-hidden="true" />
              ),
            )}
          </div>
        </section>
        <aside className="cal-side" ref={panelRef}>
          <DayDetail day={day} />
          <div className="card">
            <h2 className="card-title">Resumen del mes</h2>
            <div className="mini-stats">
              <div>
                <small>Pagado</small>
                <b className="pos">{formatMoney(totals.paid, currency, { short: true })}</b>
              </div>
              <div>
                <small>Por pagar</small>
                <b className="amber">{formatMoney(totals.pending, currency, { short: true })}</b>
              </div>
              <div>
                <small>Vencido</small>
                <b className="neg">{formatMoney(totals.overdue, currency, { short: true })}</b>
              </div>
              <div>
                <small>Ingresos</small>
                <b className="violet-text">{formatMoney(income, currency, { short: true })}</b>
                {totals.expected > 0 && (
                  <small>+ {formatMoney(totals.expected, currency, { short: true })} por cobrar</small>
                )}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
