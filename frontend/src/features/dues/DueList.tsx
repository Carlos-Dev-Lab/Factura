import type { DueItem } from '../../api/types';
import { useDialogs } from '../../context/DialogsContext';
import { useUser } from '../../hooks/queries';
import { formatMoney, parseIso, relativeDay } from '../../lib/format';

const DUE_STATE_LABEL = { pending: 'Por pagar', overdue: 'Vencido', paid: 'Pagado' } as const;

const KIND_LABEL: Record<DueItem['kind'], string> = {
  invoice: 'Factura',
  scheduled: 'Pago fijo',
  card: 'Tarjeta',
};

export function dueKindLabel(due: DueItem): string {
  if (due.direction === 'in') return 'Cobro esperado';
  return KIND_LABEL[due.kind];
}

export function dueStateLabel(due: DueItem): string {
  if (due.direction === 'in') return due.state === 'paid' ? 'Cobrado' : due.state === 'overdue' ? 'Atrasado' : 'Por cobrar';
  return DUE_STATE_LABEL[due.state];
}

function DateBox({ iso, overdue }: { iso: string | null; overdue: boolean }) {
  const d = iso ? parseIso(iso) : null;
  return (
    <div className="datebox" aria-hidden="true">
      <b className={overdue ? 'neg' : ''}>{d ? d.getDate() : '—'}</b>
      <small>{d ? d.toLocaleDateString('es-PY', { month: 'short' }).replace('.', '') : ''}</small>
    </div>
  );
}

export function PayButton({ due }: { due: DueItem }) {
  const { openPay } = useDialogs();
  if (due.state === 'paid') return null;
  const income = due.direction === 'in';
  return (
    <button
      className={`btn small ${income ? 'violet' : 'mint'}`}
      onClick={() => openPay(due)}
      aria-label={`${income ? 'Registrar cobro de' : 'Pagar'} ${due.name}`}
    >
      {income ? 'Cobrado' : 'Pagar'}
    </button>
  );
}

export function DueList({ items, emptyText }: { items: DueItem[]; emptyText: string }) {
  const { currency } = useUser();
  if (!items.length) return <div className="empty">{emptyText}</div>;
  return (
    <ul className="list">
      {items.map((due) => (
        <li key={`${due.kind}-${due.id}`} className={`item ${due.direction === 'in' ? 'due-in' : ''}`}>
          <DateBox iso={due.date} overdue={due.state === 'overdue'} />
          <span className="body">
            <b>{due.name}</b>
            <span className="amt">
              {due.estimated && <span className="muted">≈ </span>}
              {formatMoney(due.amount, currency)}
            </span>
            <small className={due.state === 'overdue' ? 'neg' : ''}>
              {due.date ? `${due.state === 'overdue' ? 'Vencido · ' : ''}${relativeDay(due.date)}` : 'Sin fecha'} ·{' '}
              {due.detail ?? dueKindLabel(due)}
            </small>
          </span>
          <PayButton due={due} />
        </li>
      ))}
    </ul>
  );
}
