import { tint } from '../../lib/format';

interface Props {
  label: string;
  value: string;
  hint: string;
  color: string;
  tone?: 'pos' | 'neg';
}

export function KpiCard({ label, value, hint, color, tone }: Props) {
  return (
    <div className="card kpi">
      <div className="row">
        <span className="muted">{label}</span>
        <span className="chip" style={{ background: tint(color, 0.2) }} aria-hidden="true">
          <span style={{ background: color }} />
        </span>
      </div>
      <div className={`num ${tone ?? ''}`}>{value}</div>
      <div className="muted small">{hint}</div>
    </div>
  );
}
