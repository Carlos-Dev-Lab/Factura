import { useEffect, useState } from 'react';

import { accountsApi } from '../../api/endpoints';
import type { TransferInput } from '../../api/types';
import { AccountSelect, Field, MoneyInput } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useActiveAccounts, useFinancialMutation } from '../../hooks/queries';
import { todayIso } from '../../lib/format';

export type TransferDraft = Partial<TransferInput>;

/** Mover plata entre cuentas propias: retirar del cajero, pagar la tarjeta, cargar la billetera. */
export function TransferDialog({ draft, onClose }: { draft: TransferDraft; onClose: () => void }) {
  const toast = useToast();
  const { data: accounts = [] } = useActiveAccounts();
  const [form, setForm] = useState<TransferInput>({
    from_account_id: draft.from_account_id ?? 0,
    to_account_id: draft.to_account_id ?? 0,
    amount: draft.amount ?? 0,
    date: draft.date ?? todayIso(),
    description: draft.description ?? '',
  });
  const set = <K extends keyof TransferInput>(k: K, v: TransferInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  // Cuenta de origen por defecto: la primera que no sea tarjeta ni el destino.
  useEffect(() => {
    if (form.from_account_id || !accounts.length) return;
    const from = accounts.find((a) => a.type !== 'card' && a.id !== form.to_account_id) ?? accounts[0];
    if (from) setForm((f) => ({ ...f, from_account_id: from.id }));
  }, [accounts, form.from_account_id, form.to_account_id]);

  const save = useFinancialMutation(accountsApi.transfer, 'Transferencia registrada');

  const submit = () => {
    if (!form.from_account_id || !form.to_account_id) return toast('Elegí las dos cuentas');
    if (form.from_account_id === form.to_account_id) return toast('Elegí dos cuentas distintas');
    if (form.amount <= 0) return toast('Ingresá un monto mayor a cero');
    save.mutate(form, { onSuccess: onClose });
  };

  if (accounts.length < 2) {
    return (
      <Modal
        title="Transferir entre cuentas"
        onClose={onClose}
        onSubmit={onClose}
        footer={
          <button className="btn mint" type="submit">
            Entendido
          </button>
        }
      >
        <div className="empty">Necesitás al menos dos cuentas. Creá una en Cuentas (por ejemplo tu banco).</div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Transferir entre cuentas"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn violet" disabled={save.isPending}>
            Transferir
          </button>
        </>
      }
    >
      <p className="muted">No cuenta como gasto ni como ingreso: solo mueve el saldo entre tus cuentas.</p>
      <MoneyInput label="Monto" value={form.amount} onChange={(v) => set('amount', v)} autoFocus />
      <div className="fgrid">
        <AccountSelect
          label="Desde"
          allowNone={false}
          value={form.from_account_id || null}
          onChange={(v) => set('from_account_id', v ?? 0)}
        />
        <AccountSelect
          label="Hacia"
          allowNone={false}
          value={form.to_account_id || null}
          onChange={(v) => set('to_account_id', v ?? 0)}
        />
        <Field label="Fecha">
          <input type="date" required value={form.date} onChange={(e) => set('date', e.target.value)} />
        </Field>
        <Field label="Detalle">
          <input
            maxLength={160}
            placeholder="Ej. Pago resumen Visa"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}
