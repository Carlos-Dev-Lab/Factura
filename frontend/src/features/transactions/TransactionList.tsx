import type { Transaction } from '../../api/types';
import { Icon } from '../../components/Icon';
import { useDialogs } from '../../context/DialogsContext';
import { useUser } from '../../hooks/queries';
import { formatDate, formatMoney, PAYMENT_METHODS, tint } from '../../lib/format';
import { toDraft } from './TransactionDialog';

const FALLBACK_COLOR = '#A3ADC8';

interface Props {
  items: Transaction[];
  emptyText: string;
  allowSchedule?: boolean;
}

export function TransactionList({ items, emptyText, allowSchedule = false }: Props) {
  const { currency } = useUser();
  const { openScheduled, openTransaction } = useDialogs();
  if (!items.length) return <div className="empty">{emptyText}</div>;
  return (
    <ul className="list">
      {items.map((t) => {
        const color = t.category?.color ?? FALLBACK_COLOR;
        const title = t.description || t.category?.name || (t.kind === 'expense' ? 'Gasto' : 'Ingreso');
        const canSchedule = allowSchedule && t.kind === 'expense' && !t.invoice_id && !t.scheduled_payment_id;
        return (
          <li key={t.id} className={canSchedule ? 'item transaction-with-schedule' : 'item'}>
            <span className="ava" style={{ background: tint(color), color }} aria-hidden="true">
              {title.charAt(0).toUpperCase()}
            </span>
            <span className="body">
              <b>{title}</b>
              <small>
                {[
                  t.category?.name,
                  formatDate(t.date),
                  t.account?.name ?? PAYMENT_METHODS[t.method],
                  allowSchedule && t.kind === 'expense' && t.scheduled_payment_id && 'Pago fijo',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </small>
            </span>
            <span className={`amt ${t.kind === 'expense' ? 'neg' : 'pos'}`}>
              {formatMoney(t.kind === 'expense' ? -t.amount : t.amount, currency, { sign: true })}
            </span>
            <button className="icon-btn" onClick={() => openTransaction(toDraft(t))} aria-label={`Editar ${title}`}>
              <Icon name="edit" size={16} />
            </button>
            {canSchedule && (
              <button
                type="button"
                className="btn small make-scheduled"
                aria-label={`Hacer fijo ${title}`}
                onClick={() => openScheduled({ expense: t })}
              >
                <Icon name="calendar" size={16} />
                Hacer fijo
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
