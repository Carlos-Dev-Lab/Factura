import { useState } from 'react';

import type { YearReport } from '../api/types';
import { Icon } from '../components/Icon';
import { Loading } from '../components/Loading';
import { useUser, useYearReport } from '../hooks/queries';
import { formatMoney } from '../lib/format';

const MONTHS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic'];
const TICKS = 4;

/** Escala "linda" para el eje: 0, 2 M, 4 M, 6 M... */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value / TICKS));
  const nice = [1, 2, 2.5, 5, 10].map((m) => m * step).find((s) => s * TICKS >= value) ?? step * 10;
  return nice * TICKS;
}

function YearChart({ report }: { report: YearReport }) {
  const { currency } = useUser();
  const [active, setActive] = useState<number | null>(null);
  const max = niceMax(Math.max(...report.months.flatMap((m) => [m.income, m.expense])));
  const ticks = Array.from({ length: TICKS + 1 }, (_, i) => (max / TICKS) * i);
  const short = (v: number) => formatMoney(v, currency, { short: true });

  return (
    <figure className="year-chart" aria-label={`Ingresos y gastos por mes de ${report.year}`}>
      <div className="chart-legend" aria-hidden="true">
        <span>
          <i className="sw income" /> Ingresos
        </span>
        <span>
          <i className="sw expense" /> Gastos
        </span>
      </div>
      <div className="plot">
        <div className="y-axis" aria-hidden="true">
          {ticks
            .slice()
            .reverse()
            .map((t) => (
              <span key={t}>{t ? short(t).replace(/^\S+ /, '') : '0'}</span>
            ))}
        </div>
        <div className="plot-area">
          <div className="gridlines" aria-hidden="true">
            {ticks.map((t) => (
              <i key={t} style={{ bottom: `${(t / max) * 100}%` }} />
            ))}
          </div>
          <div className="groups">
            {report.months.map((m, i) => (
              <button
                key={m.month}
                type="button"
                className={`group ${active === i ? 'on' : ''}`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                aria-label={`${MONTHS[i]}: ingresos ${formatMoney(m.income, currency)}, gastos ${formatMoney(m.expense, currency)}`}
              >
                <span className="pair">
                  <span className="col income" style={{ height: `${(m.income / max) * 100}%` }} />
                  <span className="col expense" style={{ height: `${(m.expense / max) * 100}%` }} />
                </span>
                {active === i && (
                  <span className="tip" role="tooltip">
                    <b>
                      {MONTHS[i]} {report.year}
                    </b>
                    <span>
                      <i className="sw income" /> Ingresos {formatMoney(m.income, currency)}
                    </span>
                    <span>
                      <i className="sw expense" /> Gastos {formatMoney(m.expense, currency)}
                    </span>
                    <span>Saldo {formatMoney(m.balance, currency)}</span>
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="x-axis" aria-hidden="true">
        {MONTHS.map((m) => (
          <span key={m}>{m}</span>
        ))}
      </div>
    </figure>
  );
}

export function ReportsPage() {
  const { currency } = useUser();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [table, setTable] = useState(false);
  const report = useYearReport(year);
  const money = (v: number) => formatMoney(v, currency);

  return (
    <div className="stack">
      <div className="toolbar">
        <div className="month-switch" role="group" aria-label="Año">
          <button className="icon-btn" onClick={() => setYear((y) => y - 1)} aria-label="Año anterior">
            <Icon name="left" size={18} stroke={2.4} />
          </button>
          <button className="month-label" onClick={() => setYear(new Date().getFullYear())} title="Volver al año actual">
            {year}
          </button>
          <button className="icon-btn" onClick={() => setYear((y) => y + 1)} aria-label="Año siguiente">
            <Icon name="right" size={18} stroke={2.4} />
          </button>
        </div>
      </div>
      {!report.data ? (
        <Loading error={report.error} />
      ) : (
        <>
          <section className="grid kpis-3">
            <div className="card kpi">
              <span className="muted">Ingresos del año</span>
              <div className="num">{money(report.data.income)}</div>
            </div>
            <div className="card kpi">
              <span className="muted">Gastos del año</span>
              <div className="num">{money(report.data.expense)}</div>
              <div className="muted small">
                {report.data.months_counted
                  ? `Promedio: ${money(report.data.average_expense)} por mes`
                  : 'Año sin meses transcurridos'}
              </div>
            </div>
            <div className="card kpi">
              <span className="muted">Saldo del año</span>
              <div className={`num ${report.data.balance < 0 ? 'neg' : 'pos'}`}>{money(report.data.balance)}</div>
            </div>
          </section>
          <section className="card">
            <div className="card-head">
              <h2>Mes a mes</h2>
              <button className="btn small" onClick={() => setTable((t) => !t)} aria-pressed={table}>
                {table ? 'Ver gráfico' : 'Ver como tabla'}
              </button>
            </div>
            {table ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Mes</th>
                      <th className="r">Ingresos</th>
                      <th className="r">Gastos</th>
                      <th className="r">Saldo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.data.months.map((m, i) => (
                      <tr key={m.month}>
                        <td>{MONTHS[i]}</td>
                        <td className="r num">{money(m.income)}</td>
                        <td className="r num">{money(m.expense)}</td>
                        <td className={`r num ${m.balance < 0 ? 'neg' : ''}`}>{money(m.balance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <YearChart report={report.data} />
            )}
          </section>
          <section className="card">
            <div className="card-head">
              <h2>Gastos por categoría</h2>
              <span className="muted">{year}</span>
            </div>
            {report.data.categories.length ? (
              <ul className="cat-year">
                {report.data.categories.map((c) => {
                  const share = report.data.expense ? (c.total / report.data.expense) * 100 : 0;
                  const avg = report.data.months_counted ? c.total / report.data.months_counted : 0;
                  return (
                    <li key={c.category_id ?? 'none'}>
                      <div className="row-between">
                        <span className="budget-name">
                          <i style={{ background: c.color }} aria-hidden="true" />
                          {c.name}
                        </span>
                        <b className="num">{money(c.total)}</b>
                      </div>
                      <div className="share" aria-hidden="true">
                        <div style={{ width: `${share}%`, background: c.color }} />
                      </div>
                      <span className="hint">
                        {share.toFixed(1)}% de los gastos · {money(avg)} por mes en promedio
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="empty">No hay gastos registrados en {year}.</div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
