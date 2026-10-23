import type { MonthSummary } from '../../api/types';
import { useUser } from '../../hooks/queries';
import { formatMoney } from '../../lib/format';

const MAX_LEGEND = 6;

export function CategoryDonut({ data }: { data: MonthSummary['by_category'] }) {
  const { currency } = useUser();
  const total = data.reduce((s, c) => s + c.amount, 0);
  let acc = 0;
  const gradient = total
    ? data
        .map((c) => {
          const from = acc;
          acc += (c.amount / total) * 100;
          return `${c.color} ${from}% ${acc}%`;
        })
        .join(', ')
    : '#1F2946 0 100%';

  return (
    <>
      <div
        className="donut"
        style={{ background: `conic-gradient(${gradient})` }}
        role="img"
        aria-label={`Gastos por categoría: ${data.map((c) => c.name).join(', ') || 'sin datos'}`}
      >
        <div className="hole">
          <div className="num">{formatMoney(total, currency, { short: true })}</div>
          <small className="muted">en gastos</small>
        </div>
      </div>
      {data.length ? (
        <ul className="legend">
          {data.slice(0, MAX_LEGEND).map((c) => (
            <li key={c.category_id ?? 'none'} className="it">
              <span className="sw" style={{ background: c.color }} />
              <span>{c.name}</span>
              <span className="muted">{Math.round((c.amount / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">Todavía no hay gastos este mes.</div>
      )}
    </>
  );
}
