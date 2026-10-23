import { useState } from 'react';

import { scheduledApi } from '../../api/endpoints';
import type { ScheduledInput, ScheduledPayment, TransactionKind } from '../../api/types';
import { AccountSelect, CategorySelect, ConfirmDeleteButton, Field, MoneyInput, Switch } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useFinancialMutation, useUser } from '../../hooks/queries';
import { formatMoney, monthLabel, monthOf, shiftMonth, todayIso } from '../../lib/format';

export type ScheduledDialogState = { payment: ScheduledPayment } | { dayOfMonth: number; kind?: TransactionKind };

const monthsBetween = (a: string, b: string) => {
  const [ya = 0, ma = 1] = a.split('-').map(Number);
  const [yb = 0, mb = 1] = b.split('-').map(Number);
  return (yb - ya) * 12 + (mb - ma);
};

export function ScheduledDialog({ state, onClose }: { state: ScheduledDialogState; onClose: () => void }) {
  const { currency } = useUser();
  const toast = useToast();
  const existing = 'payment' in state ? state.payment : undefined;
  const [form, setForm] = useState<ScheduledInput>(
    existing
      ? {
          name: existing.name,
          kind: existing.kind,
          amount: existing.amount,
          variable_amount: existing.variable_amount,
          day_of_month: existing.day_of_month,
          start_month: existing.start_month,
          end_month: existing.end_month,
          active: existing.active,
          category_id: existing.category?.id ?? null,
          account_id: existing.account_id,
        }
      : {
          name: '',
          kind: ('kind' in state && state.kind) || 'expense',
          amount: 0,
          variable_amount: false,
          day_of_month: 'dayOfMonth' in state ? state.dayOfMonth : 1,
          start_month: monthOf(todayIso()),
          end_month: null,
          category_id: null,
          account_id: null,
          active: true,
        },
  );
  const set = <K extends keyof ScheduledInput>(k: K, v: ScheduledInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const installments = form.end_month ? monthsBetween(form.start_month, form.end_month) + 1 : 0;
  const isIncome = form.kind === 'income';

  const save = useFinancialMutation(
    (data: ScheduledInput) => (existing ? scheduledApi.update(existing.id, data) : scheduledApi.create(data)),
    isIncome ? 'Cobro fijo guardado' : 'Pago fijo guardado',
  );
  const remove = useFinancialMutation(() => scheduledApi.remove(existing!.id), 'Pago fijo eliminado');

  const setInstallments = (n: number) =>
    set('end_month', n > 0 ? shiftMonth(form.start_month, Math.min(n, 360) - 1) : null);

  const submit = () => {
    if (form.amount <= 0) return toast('Ingresá un monto mayor a cero');
    if (form.end_month && form.end_month < form.start_month) return toast('La última cuota no puede ser antes de la primera');
    save.mutate(form, { onSuccess: onClose });
  };

  return (
    <Modal
      title={existing ? (isIncome ? 'Editar cobro fijo' : 'Editar pago fijo') : isIncome ? 'Nuevo cobro fijo' : 'Nuevo pago fijo'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {existing && <ConfirmDeleteButton onConfirm={() => remove.mutate(undefined, { onSuccess: onClose })} />}
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn mint" disabled={save.isPending}>
            Guardar
          </button>
        </>
      }
    >
      <div className="tabs-type" role="group" aria-label="Tipo">
        {(['expense', 'income'] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={`${k} ${form.kind === k ? 'on' : ''}`}
            aria-pressed={form.kind === k}
            onClick={() => setForm((f) => ({ ...f, kind: k, category_id: null }))}
          >
            {k === 'expense' ? 'Pago (gasto)' : 'Cobro (ingreso)'}
          </button>
        ))}
      </div>
      <Field label="Nombre">
        <input
          required
          data-autofocus
          maxLength={80}
          placeholder={isIncome ? 'Ej. Sueldo' : 'Ej. Alquiler, ANDE, cuota del auto'}
          value={form.name}
          onChange={(e) => set('name', e.target.value)}
        />
      </Field>
      <div className="fgrid">
        <MoneyInput
          label={form.variable_amount ? 'Monto estimado' : 'Monto'}
          value={form.amount}
          onChange={(v) => set('amount', v)}
          hint={form.variable_amount ? 'Al pagar se pregunta el monto real de cada mes.' : undefined}
        />
        <Field label="Día del mes">
          <input
            type="number"
            min={1}
            max={31}
            required
            value={form.day_of_month}
            onChange={(e) => set('day_of_month', Number(e.target.value))}
          />
        </Field>
        <CategorySelect kind={form.kind} value={form.category_id} onChange={(v) => set('category_id', v)} />
        <AccountSelect
          label={isIncome ? 'Cuenta donde entra' : 'Cuenta de la que sale'}
          value={form.account_id}
          onChange={(v) => set('account_id', v)}
        />
      </div>
      <div className="switch-row">
        <div>
          <b>El monto cambia cada mes</b>
          <span className="hint">Servicios como ANDE, ESSAP o internet: se confirma el monto al pagar.</span>
        </div>
        <Switch
          checked={form.variable_amount}
          label="El monto cambia cada mes"
          onChange={(v) => set('variable_amount', v)}
        />
      </div>
      <div className="fgrid">
        <Field label="Desde">
          <input
            type="month"
            required
            value={form.start_month}
            onChange={(e) => {
              const start = e.target.value;
              if (!start) return;
              // Al mover el inicio de un plan de cuotas, se mantiene la cantidad de cuotas.
              setForm((f) => ({
                ...f,
                start_month: start,
                end_month: f.end_month ? shiftMonth(start, Math.max(0, installments - 1)) : null,
              }));
            }}
          />
        </Field>
        <Field
          label="Cantidad de cuotas"
          hint={
            installments
              ? `Última cuota: ${monthLabel(form.end_month!).toLowerCase()} · total ${formatMoney(form.amount * installments, currency)}`
              : 'Vacío = se repite todos los meses, sin fin.'
          }
        >
          <input
            type="number"
            min={0}
            max={360}
            placeholder="Sin fin"
            value={installments || ''}
            onChange={(e) => setInstallments(Number(e.target.value) || 0)}
          />
        </Field>
      </div>
      <div className="switch-row">
        <div>
          <b>Activo</b>
          <span className="hint">Pausalo para que deje de aparecer sin perder el historial.</span>
        </div>
        <Switch checked={form.active} label="Activo" onChange={(v) => set('active', v)} />
      </div>
    </Modal>
  );
}
