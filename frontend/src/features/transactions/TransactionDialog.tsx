import { useEffect, useRef, useState } from 'react';

import { transactionsApi } from '../../api/endpoints';
import type { PaymentMethod, Transaction, TransactionInput, TransactionKind } from '../../api/types';
import { AccountSelect, CategorySelect, ConfirmDeleteButton, Field, MoneyInput } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useActiveAccounts, useCategories, useFinancialMutation } from '../../hooks/queries';
import { SUGGESTION_SOURCE, useCategorySuggestion } from '../../hooks/useSuggestion';
import { PAYMENT_METHODS } from '../../lib/format';

export type TransactionDraft = Partial<TransactionInput> & { id?: number; linked?: 'invoice' | 'scheduled' };

export const toDraft = (t: Transaction): TransactionDraft => ({
  id: t.id,
  kind: t.kind,
  amount: t.amount,
  date: t.date,
  description: t.description,
  method: t.method,
  category_id: t.category?.id ?? null,
  account_id: t.account?.id ?? null,
  linked: t.invoice_id ? 'invoice' : t.scheduled_payment_id ? 'scheduled' : undefined,
});

interface Props {
  initial: TransactionDraft;
  defaultDate: string;
  onClose: () => void;
}

export function TransactionDialog({ initial, defaultDate, onClose }: Props) {
  const isNew = initial.id === undefined;
  const { data: categories } = useCategories();
  const { data: accounts } = useActiveAccounts();
  const toast = useToast();
  const [form, setForm] = useState<TransactionInput>({
    kind: initial.kind ?? 'expense',
    amount: initial.amount ?? 0,
    date: initial.date ?? defaultDate,
    description: initial.description ?? '',
    method: initial.method ?? 'cash',
    category_id: initial.category_id ?? null,
    account_id: initial.account_id ?? null,
  });
  const set = <K extends keyof TransactionInput>(k: K, v: TransactionInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  // Una vez que el usuario elige la categoría a mano, no se la cambia nada automático.
  const [categoryTouched, setCategoryTouched] = useState(!isNew || initial.category_id !== undefined);
  // Tipo para el que ya se sugirió la primera categoría (se hace una sola vez por tipo).
  const suggestedFor = useRef<TransactionKind | null>(null);
  const suggestion = useCategorySuggestion(form.kind, form.description, isNew && !categoryTouched);

  // En un movimiento nuevo sin categoría, preselecciona la primera del tipo elegido.
  useEffect(() => {
    if (!isNew || !categories || suggestedFor.current === form.kind) return;
    suggestedFor.current = form.kind;
    if (form.category_id !== null) return;
    const first = categories.find((c) => c.kind === form.kind);
    if (first) setForm((f) => ({ ...f, category_id: first.id }));
  }, [isNew, form.kind, form.category_id, categories]);

  // Lo que el usuario eligió antes para una descripción parecida tiene prioridad.
  useEffect(() => {
    if (suggestion?.category_id && !categoryTouched) setForm((f) => ({ ...f, category_id: suggestion.category_id }));
  }, [suggestion, categoryTouched]);

  // Cuenta por defecto: la primera activa.
  useEffect(() => {
    if (isNew && initial.account_id === undefined && accounts?.length) {
      setForm((f) => (f.account_id === null ? { ...f, account_id: accounts[0]!.id } : f));
    }
  }, [isNew, initial.account_id, accounts]);

  const save = useFinancialMutation(
    (data: TransactionInput) => (isNew ? transactionsApi.create(data) : transactionsApi.update(initial.id!, data)),
    'Movimiento guardado',
  );
  const remove = useFinancialMutation(() => transactionsApi.remove(initial.id!), 'Movimiento eliminado');

  const switchKind = (kind: TransactionKind) => {
    setCategoryTouched(false);
    setForm((f) => ({ ...f, kind, category_id: null }));
  };

  const chooseAccount = (id: number | null) => {
    const account = accounts?.find((a) => a.id === id);
    // Un gasto con tarjeta de crédito es, obviamente, con crédito.
    setForm((f) => ({ ...f, account_id: id, method: account?.type === 'card' ? 'credit' : f.method }));
  };

  const linkedNote =
    initial.linked === 'invoice'
      ? 'Es el pago de una factura: el monto y la fecha también se actualizan en la factura.'
      : initial.linked === 'scheduled'
        ? 'Es el pago de un pago fijo: la fecha tiene que quedar dentro del mismo mes.'
        : null;

  return (
    <Modal
      title={isNew ? 'Nuevo movimiento' : 'Editar movimiento'}
      onClose={onClose}
      onSubmit={() =>
        form.amount > 0 ? save.mutate(form, { onSuccess: onClose }) : toast('Ingresá un monto mayor a cero')
      }
      footer={
        <>
          {!isNew && <ConfirmDeleteButton onConfirm={() => remove.mutate(undefined, { onSuccess: onClose })} />}
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className={`btn ${form.kind === 'expense' ? 'coral' : 'mint'}`} disabled={save.isPending}>
            Guardar
          </button>
        </>
      }
    >
      <div className="tabs-type" role="group" aria-label="Tipo de movimiento">
        {(['expense', 'income'] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={`${k} ${form.kind === k ? 'on' : ''}`}
            aria-pressed={form.kind === k}
            disabled={!!initial.linked && form.kind !== k}
            onClick={() => switchKind(k)}
          >
            {k === 'expense' ? 'Gasto' : 'Ingreso'}
          </button>
        ))}
      </div>
      {linkedNote && <p className="hint">{linkedNote}</p>}
      <MoneyInput label="Monto" value={form.amount} onChange={(v) => set('amount', v)} autoFocus />
      <Field label="Descripción">
        <input
          maxLength={160}
          placeholder={form.kind === 'expense' ? 'Ej. Biggie, almuerzo, nafta' : 'Ej. Sueldo, venta'}
          value={form.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </Field>
      <div className="fgrid">
        <CategorySelect
          kind={form.kind}
          value={form.category_id}
          onChange={(v) => {
            setCategoryTouched(true);
            set('category_id', v);
          }}
          hint={
            suggestion?.source && !categoryTouched && suggestion.category_id === form.category_id
              ? SUGGESTION_SOURCE[suggestion.source]
              : undefined
          }
        />
        <Field label="Fecha">
          <input type="date" required value={form.date} onChange={(e) => set('date', e.target.value)} />
        </Field>
        <AccountSelect value={form.account_id} onChange={chooseAccount} />
        <Field label="Método">
          <select value={form.method} onChange={(e) => set('method', e.target.value as PaymentMethod)}>
            {Object.entries(PAYMENT_METHODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </Modal>
  );
}
