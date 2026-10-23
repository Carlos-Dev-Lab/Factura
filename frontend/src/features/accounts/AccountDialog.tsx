import { useState } from 'react';

import { accountsApi } from '../../api/endpoints';
import type { Account, AccountInput, AccountType } from '../../api/types';
import { Field, MoneyInput } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useFinancialMutation } from '../../hooks/queries';
import { ACCOUNT_TYPES } from '../../lib/format';

export type AccountDialogState = { account: Account } | { type?: AccountType };

const PALETTE = ['#3EE6B0', '#5AB8FF', '#8B7BFF', '#FFC24D', '#FF8A5B', '#FF6B9A', '#4DD4E6', '#A3ADC8'];

export function AccountDialog({ state, onClose }: { state: AccountDialogState; onClose: () => void }) {
  const toast = useToast();
  const existing = 'account' in state ? state.account : undefined;
  const [form, setForm] = useState<AccountInput>(
    existing
      ? {
          name: existing.name,
          type: existing.type,
          color: existing.color,
          opening_balance: existing.opening_balance,
          closing_day: existing.closing_day,
          due_day: existing.due_day,
          credit_limit: existing.credit_limit,
        }
      : {
          name: '',
          type: ('type' in state && state.type) || 'bank',
          color: PALETTE[1]!,
          opening_balance: 0,
          closing_day: null,
          due_day: null,
          credit_limit: null,
        },
  );
  const set = <K extends keyof AccountInput>(k: K, v: AccountInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const isCard = form.type === 'card';
  // En una tarjeta se carga la deuda inicial como número positivo; se guarda como saldo negativo.
  const [debt, setDebt] = useState(() => (existing && isCard ? Math.max(0, -existing.opening_balance) : 0));

  const save = useFinancialMutation(
    (data: AccountInput) => (existing ? accountsApi.update(existing.id, data) : accountsApi.create(data)),
    existing ? 'Cuenta actualizada' : 'Cuenta creada',
  );
  const archive = useFinancialMutation(
    () => accountsApi.update(existing!.id, { archived: !existing!.archived }),
    existing?.archived ? 'Cuenta reactivada' : 'Cuenta archivada',
  );
  const remove = useFinancialMutation(() => accountsApi.remove(existing!.id), 'Cuenta eliminada');

  const submit = () => {
    if (!form.name.trim()) return toast('Poné un nombre a la cuenta');
    if (isCard && (!form.closing_day || !form.due_day)) return toast('Indicá el día de cierre y de vencimiento');
    const data = { ...form, name: form.name.trim(), opening_balance: isCard ? -debt : form.opening_balance };
    save.mutate(data, { onSuccess: onClose });
  };

  const dayInput = (key: 'closing_day' | 'due_day', label: string, hint: string) => (
    <Field label={label} hint={hint}>
      <input
        type="number"
        min={1}
        max={31}
        required
        value={form[key] ?? ''}
        onChange={(e) => set(key, e.target.value ? Number(e.target.value) : null)}
      />
    </Field>
  );

  return (
    <Modal
      title={existing ? 'Editar cuenta' : 'Nueva cuenta'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {existing && existing.movement_count === 0 && (
            <button type="button" className="btn danger" onClick={() => remove.mutate(undefined, { onSuccess: onClose })}>
              Eliminar
            </button>
          )}
          {existing && existing.movement_count > 0 && (
            <button type="button" className="btn" onClick={() => archive.mutate(undefined, { onSuccess: onClose })}>
              {existing.archived ? 'Reactivar' : 'Archivar'}
            </button>
          )}
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn mint" disabled={save.isPending}>
            Guardar
          </button>
        </>
      }
    >
      {!existing && (
        <div className="seg wide four" role="radiogroup" aria-label="Tipo de cuenta">
          {(Object.keys(ACCOUNT_TYPES) as AccountType[]).map((t) => (
            <button
              type="button"
              key={t}
              role="radio"
              aria-checked={form.type === t}
              className={form.type === t ? 'on' : ''}
              onClick={() => set('type', t)}
            >
              {ACCOUNT_TYPES[t]}
            </button>
          ))}
        </div>
      )}
      <Field label="Nombre">
        <input
          required
          data-autofocus
          maxLength={60}
          placeholder={isCard ? 'Ej. Visa Itaú' : 'Ej. Cuenta Itaú'}
          value={form.name}
          onChange={(e) => set('name', e.target.value)}
        />
      </Field>
      {isCard ? (
        <>
          <div className="fgrid">
            {dayInput('closing_day', 'Día de cierre', 'Último día de consumos del resumen.')}
            {dayInput('due_day', 'Día de vencimiento', 'Día límite para pagar el resumen.')}
          </div>
          <div className="fgrid">
            <MoneyInput
              label="Límite de crédito"
              value={form.credit_limit ?? 0}
              onChange={(v) => set('credit_limit', v || null)}
            />
            <MoneyInput
              label={existing ? 'Deuda al empezar a usar la app' : 'Deuda actual de la tarjeta'}
              value={debt}
              onChange={setDebt}
              hint="Lo que debías antes de registrar movimientos aquí."
            />
          </div>
        </>
      ) : (
        <MoneyInput
          label={existing ? 'Saldo inicial' : 'Saldo actual'}
          value={form.opening_balance}
          onChange={(v) => set('opening_balance', v)}
          hint="Lo que hay hoy en la cuenta. Después se actualiza solo con cada movimiento."
        />
      )}
      <div className="f">
        <span>Color</span>
        <div className="palette" role="radiogroup" aria-label="Color">
          {PALETTE.map((c) => (
            <button
              type="button"
              key={c}
              role="radio"
              aria-checked={form.color === c}
              aria-label={`Color ${c}`}
              className={form.color === c ? 'on' : ''}
              style={{ background: c }}
              onClick={() => set('color', c)}
            />
          ))}
        </div>
      </div>
    </Modal>
  );
}
