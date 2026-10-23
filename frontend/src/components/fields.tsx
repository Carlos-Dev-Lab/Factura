import { useEffect, useState, type ReactNode } from 'react';

import type { Category, TransactionKind } from '../api/types';
import { useActiveAccounts, useCategories, useUser } from '../hooks/queries';
import { currencySymbol, groupDigits, moneyInputText, parseMoney } from '../lib/format';
import { Icon } from './Icon';

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="f">
      {label}
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

interface MoneyInputProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  autoFocus?: boolean;
  hint?: string;
}

/** Campo de monto con separador de miles. `value` es solo el valor inicial. */
export function MoneyInput({ label, value, onChange, autoFocus, hint }: MoneyInputProps) {
  const { currency } = useUser();
  const [text, setText] = useState(() => moneyInputText(value, currency));

  return (
    <Field label={label} hint={hint}>
      <input
        className="big"
        inputMode="decimal"
        autoComplete="off"
        placeholder={`${currencySymbol(currency)} 0`}
        value={text}
        data-autofocus={autoFocus || undefined}
        onChange={(e) => {
          const next = groupDigits(e.target.value, currency);
          setText(next);
          onChange(parseMoney(next));
        }}
      />
    </Field>
  );
}

interface CategorySelectProps {
  kind: TransactionKind;
  value: number | null;
  onChange: (id: number | null) => void;
  hint?: string;
}

export function CategorySelect({ kind, value, onChange, hint }: CategorySelectProps) {
  const { data = [] } = useCategories();
  const options = data.filter((c: Category) => c.kind === kind);
  return (
    <Field label="Categoría" hint={hint}>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Sin categoría</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </Field>
  );
}

interface AccountSelectProps {
  value: number | null;
  onChange: (id: number | null) => void;
  label?: string;
  /** Permitir "Sin cuenta" (por ejemplo para movimientos viejos). */
  allowNone?: boolean;
  exclude?: number | null;
}

export function AccountSelect({ value, onChange, label = 'Cuenta', allowNone = true, exclude }: AccountSelectProps) {
  const { data = [] } = useActiveAccounts();
  const options = data.filter((a) => a.id !== exclude);
  return (
    <Field label={label}>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        {allowNone && <option value="">Sin cuenta</option>}
        {options.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
    </Field>
  );
}

interface ConfirmDeleteProps {
  onConfirm: () => void;
  label?: string;
  /** Versión compacta: ícono de papelera que se expande a "¿Confirmar?". */
  compact?: boolean;
}

/** Botón de borrado que pide un segundo toque para confirmar. */
export function ConfirmDeleteButton({ onConfirm, label = 'Eliminar', compact = false }: ConfirmDeleteProps) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = window.setTimeout(() => setArmed(false), 3000);
    return () => window.clearTimeout(t);
  }, [armed]);
  return (
    <button
      type="button"
      className={`btn danger ${compact ? 'small compact' : ''} ${armed ? 'armed' : ''}`}
      aria-label={compact && !armed ? label : undefined}
      onClick={() => (armed ? onConfirm() : setArmed(true))}
    >
      {armed ? (compact ? '¿Confirmar?' : '¿Seguro? Tocá de nuevo') : compact ? <Icon name="trash" size={16} /> : label}
    </button>
  );
}

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}

/** Interruptor accesible (role="switch"). */
export function Switch({ checked, onChange, label, disabled }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`switch ${checked ? 'on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  );
}
