import { useEffect, useState } from 'react';

import { invoicesApi, scheduledApi } from '../../api/endpoints';
import type { DueItem, PaymentMethod } from '../../api/types';
import { AccountSelect, Field, MoneyInput } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useActiveAccounts, useFinancialMutation, usePaymentHistory, useScheduled, useUser } from '../../hooks/queries';
import { formatMoney, monthOf, PAYMENT_METHODS, todayIso } from '../../lib/format';

/** Para pagos de un mes pasado, la fecha tiene que quedar dentro de ese mes. */
function defaultDate(due: DueItem): string {
  const today = todayIso();
  if (!due.date || monthOf(due.date) === monthOf(today)) return today;
  return due.date;
}

function VariationHint({ paymentId, amount }: { paymentId: number; amount: number }) {
  const { currency } = useUser();
  const { data } = usePaymentHistory(paymentId);
  if (!data?.average) return <span className="hint">Primer pago registrado: no hay meses anteriores para comparar.</span>;
  const diff = data.average ? Math.round(((amount - data.average) / data.average) * 100) : 0;
  const tone = diff >= 15 ? 'neg' : diff <= -15 ? 'pos' : '';
  return (
    <span className="hint">
      Último: {formatMoney(data.last_amount ?? 0, currency)} · Promedio: {formatMoney(data.average, currency)}
      {amount > 0 && Math.abs(diff) >= 5 && (
        <b className={tone}>
          {' '}
          · {diff > 0 ? '+' : ''}
          {diff}% vs. promedio
        </b>
      )}
    </span>
  );
}

export function PayDialog({ due, onClose }: { due: DueItem; onClose: () => void }) {
  const { currency } = useUser();
  const toast = useToast();
  const { data: scheduled = [] } = useScheduled();
  const { data: accounts = [] } = useActiveAccounts();
  const payment = due.kind === 'scheduled' ? scheduled.find((s) => s.id === due.id) : undefined;
  const isIncome = due.direction === 'in';

  const [amount, setAmount] = useState(due.amount);
  const [date, setDate] = useState(() => defaultDate(due));
  const [method, setMethod] = useState<PaymentMethod>('transfer');
  const preferred = payment?.account_id ?? accounts.find((a) => a.type !== 'card')?.id ?? accounts[0]?.id ?? null;
  const [accountId, setAccountId] = useState<number | null>(preferred);
  const [touchedAccount, setTouchedAccount] = useState(false);
  // Las cuentas y los pagos fijos pueden llegar después de abrir el diálogo.
  useEffect(() => {
    if (!touchedAccount) setAccountId(preferred);
  }, [preferred, touchedAccount]);

  const pay = useFinancialMutation(
    (): Promise<unknown> =>
      due.kind === 'invoice'
        ? invoicesApi.pay(due.id, { method, paid_on: date, account_id: accountId })
        : scheduledApi.pay(due.id, monthOf(due.date ?? date), { method, paid_on: date, account_id: accountId, amount }),
    isIncome ? 'Cobro registrado' : 'Pago registrado',
  );

  const month = monthOf(due.date ?? todayIso());
  const outsideMonth = due.kind === 'scheduled' && monthOf(date) !== month;

  return (
    <Modal
      title={isIncome ? `Registrar cobro · ${due.name}` : `Pagar ${due.name}`}
      onClose={onClose}
      onSubmit={() => {
        if (amount <= 0) return toast('Ingresá un monto mayor a cero');
        if (outsideMonth) return toast('La fecha tiene que estar dentro del mes del pago');
        pay.mutate(undefined, { onSuccess: onClose });
      }}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className={`btn ${isIncome ? 'mint' : 'coral'}`} disabled={pay.isPending}>
            {isIncome ? 'Registrar cobro' : 'Registrar pago'}
          </button>
        </>
      }
    >
      {due.detail && <div className="found mid">{due.detail}</div>}
      {due.kind === 'invoice' ? (
        <div className="pay-amount">
          <span className="muted">Monto de la factura</span>
          <span className="num xl">{formatMoney(due.amount, currency)}</span>
          <span className="hint">Para cambiarlo, editá la factura.</span>
        </div>
      ) : (
        <div>
          <MoneyInput
            label={due.estimated ? 'Monto de este mes (el que vino en la factura)' : 'Monto'}
            value={amount}
            onChange={setAmount}
            autoFocus={due.estimated}
          />
          <VariationHint paymentId={due.id} amount={amount} />
        </div>
      )}
      <div className="fgrid">
        <Field label={isIncome ? 'Fecha del cobro' : 'Fecha del pago'}>
          <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Método">
          <select value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <AccountSelect
          label={isIncome ? 'Cuenta donde entra' : 'Cuenta de la que sale'}
          value={accountId}
          onChange={(id) => {
            setTouchedAccount(true);
            setAccountId(id);
          }}
        />
      </div>
    </Modal>
  );
}
