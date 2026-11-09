import { useEffect, useId, useState, type ReactNode } from 'react';

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
  kind?: TransactionKind;
  value: number | null;
  onChange: (id: number | null) => void;
  hint?: string;
  emptyLabel?: string;
}

export function CategorySelect({ kind, value, onChange, hint, emptyLabel = 'Sin categoría' }: CategorySelectProps) {
  const { data = [] } = useCategories();
  const options = data.filter((c: Category) => !kind || c.kind === kind);
  const id = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const selected = options.find((c) => c.id === value);
  const matches = options.filter((c) => c.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const choices = query.trim() ? matches : [{ id: null, name: emptyLabel }, ...matches];
  const choose = (id: number | null) => { onChange(id); setOpen(false); setQuery(''); setActive(0); };
  return (
    <div className="f category-field" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) { setOpen(false); setQuery(''); } }}>
      <label htmlFor={id}>Categoría</label>
      <div className="category-combobox">
        <input id={id} role="combobox" aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list"
          aria-activedescendant={open && choices[active] ? `${id}-option-${active}` : undefined}
          autoComplete="off" placeholder="Buscar categoría" value={open ? query : (selected?.name ?? emptyLabel)}
          onFocus={() => { setOpen(true); setQuery(''); setActive(0); }}
          onClick={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((n) => Math.max(0, Math.min(n + 1, choices.length - 1))); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((n) => Math.max(n - 1, 0)); }
            else if (e.key === 'Enter' && open) { e.preventDefault(); if (choices[active]) choose(choices[active].id); }
            else if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); setQuery(''); }
          }} />
        {open && <ul id={`${id}-list`} role="listbox" className="category-options">
          {choices.map((c, i) => <li key={c.id ?? 'none'} id={`${id}-option-${i}`} role="option" aria-selected={value === c.id}
            className={i === active ? 'active' : ''} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(c.id)}>{c.name}</li>)}
          {matches.length === 0 && <li className="category-empty">Sin resultados</li>}
        </ul>}
      </div>
      {hint && <span className="hint">{hint}</span>}
    </div>
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
