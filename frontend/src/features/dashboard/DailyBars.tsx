import { Link } from 'react-router-dom';

import type { MonthSummary } from '../../api/types';
import { useUser } from '../../hooks/queries';
import { formatDate, formatMoney, todayIso } from '../../lib/format';

export function DailyBars({ daily, limit }: { daily: MonthSummary['daily']; limit: number }) {
  const { currency } = useUser();
  const today = todayIso();
  const max = Math.max(1, limit, ...daily.map((d) => d.expense));
  const mid = daily[Math.floor(daily.length / 2)];

  return (
    <>
      <div className="limit-line">
        <div className="bars">
          {daily.map((d) => {
            const label = `${formatDate(d.date)}: ${formatMoney(d.expense, currency)}`;
            const cls = d.date === today ? 'today' : limit && d.expense > limit ? 'over' : '';
            return (
              <div key={d.date} className="col">
                <span className="tip">{label}</span>
                <Link
                  to={`/gastos?dia=${d.date}`}
                  className={`bar ${cls}`}
                  style={{ height: `${(d.expense / max) * 100}%` }}
                  aria-label={label}
                />
              </div>
            );
          })}
        </div>
        {limit > 0 && (
          <div className="ll" style={{ bottom: `${(limit / max) * 100}%` }}>
            <span>Límite diario</span>
          </div>
        )}
      </div>
      <div className="axis">
        <span>{formatDate(daily[0]?.date ?? null)}</span>
        <span>{formatDate(mid?.date ?? null)}</span>
        <span>{formatDate(daily.at(-1)?.date ?? null)}</span>
      </div>
    </>
  );
}
