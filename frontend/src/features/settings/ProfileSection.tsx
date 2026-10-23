import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { authApi } from '../../api/endpoints';
import type { Currency } from '../../api/types';
import { Field, MoneyInput } from '../../components/fields';
import { keys, useFinancialMutation, useSummary, useUser } from '../../hooks/queries';
import { CURRENCIES, currencySymbol, formatMoney, monthOf, todayIso } from '../../lib/format';
import { CategoryBudgets } from './CategoryBudgets';
import { SectionHeader } from './SectionHeader';

const DAYS_PER_MONTH = 30;

export function ProfileSection() {
  const user = useUser();
  const qc = useQueryClient();
  const summary = useSummary(monthOf(todayIso()));
  const initial = {
    name: user.name,
    currency: user.currency,
    monthly_budget: user.monthly_budget,
    daily_limit: user.daily_limit,
  };
  const [form, setForm] = useState(initial);
  // Clave para reiniciar los campos de monto al descartar cambios.
  const [resetKey, setResetKey] = useState(0);
  const dirty = (Object.keys(initial) as (keyof typeof initial)[]).some((k) => form[k] !== initial[k]);
  const save = useFinancialMutation(authApi.updateProfile, 'Cambios guardados');

  const spent = summary.data?.expense ?? 0;
  const usedPct = form.monthly_budget ? Math.round((spent / form.monthly_budget) * 100) : null;
  const meter = usedPct === null ? '' : usedPct >= 100 ? 'bad' : usedPct >= 80 ? 'warn' : '';
  const suggestedDaily = form.monthly_budget ? Math.round(form.monthly_budget / DAYS_PER_MONTH) : 0;
  const money = (v: number) => formatMoney(v, form.currency);

  const discard = () => {
    setForm(initial);
    setResetKey((k) => k + 1);
  };

  return (
    <div className="stack">
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(form, {
          onSuccess: (u) => {
            qc.setQueryData(keys.me, u);
          },
        });
      }}
    >
      <section className="card">
        <SectionHeader
          title="Perfil"
          description="Cómo te saluda la aplicación y en qué moneda se muestran los montos."
        />
        <div className="profile-head">
          <span className="avatar" aria-hidden="true">
            {(form.name || user.email).charAt(0).toUpperCase()}
          </span>
          <div className="profile-id">
            <b>{form.name || 'Sin nombre'}</b>
            <span className="muted">{user.email}</span>
          </div>
        </div>
        <div className="form">
          <Field label="Tu nombre">
            <input
              maxLength={80}
              placeholder="¿Cómo querés que te llamemos?"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <fieldset className="f plain">
            <legend>Moneda</legend>
            <div className="seg wide" role="radiogroup" aria-label="Moneda">
              {CURRENCIES.map((c: Currency) => (
                <button
                  type="button"
                  key={c}
                  role="radio"
                  aria-checked={form.currency === c}
                  className={form.currency === c ? 'on' : ''}
                  onClick={() => setForm({ ...form, currency: c })}
                >
                  <b>{currencySymbol(c)}</b>
                  <span>{c}</span>
                </button>
              ))}
            </div>
            <span className="hint">Solo cambia cómo se muestran los montos; no convierte valores.</span>
          </fieldset>
        </div>
      </section>

      <section className="card">
        <SectionHeader
          title="Presupuesto"
          description="Definí cuánto querés gastar. El panel te avisa cuando te acercás al límite."
        />
        <div className="fgrid" key={resetKey}>
          <MoneyInput
            label="Presupuesto mensual"
            value={form.monthly_budget}
            onChange={(v) => setForm((f) => ({ ...f, monthly_budget: v }))}
            hint="Total que planeás gastar en el mes. 0 = sin presupuesto."
          />
          <MoneyInput
            label="Límite diario"
            value={form.daily_limit}
            onChange={(v) => setForm((f) => ({ ...f, daily_limit: v }))}
            hint={
              suggestedDaily
                ? `Sugerido según tu presupuesto: ${money(suggestedDaily)} por día.`
                : 'Gasto máximo recomendado por día.'
            }
          />
        </div>
        {usedPct !== null && (
          <div className="budget-preview">
            <div className="row-between">
              <span className="soft">Este mes llevás gastado</span>
              <b>
                {money(spent)} <span className="muted">de {money(form.monthly_budget)}</span>
              </b>
            </div>
            <div className={`meter ${meter}`}>
              <div style={{ width: `${Math.min(100, usedPct)}%` }} />
            </div>
            <span className="hint">
              {usedPct >= 100
                ? `Superaste el presupuesto por ${money(spent - form.monthly_budget)}.`
                : `Te quedan ${money(form.monthly_budget - spent)} (${100 - usedPct}% disponible).`}
            </span>
          </div>
        )}
      </section>

      <div className={`savebar ${dirty ? 'show' : ''}`} aria-hidden={!dirty}>
        <span className="soft">Tenés cambios sin guardar</span>
        <div className="row-actions">
          <button type="button" className="btn" onClick={discard} tabIndex={dirty ? 0 : -1}>
            Descartar
          </button>
          <button className="btn mint" disabled={!dirty || save.isPending} tabIndex={dirty ? 0 : -1}>
            Guardar cambios
          </button>
        </div>
      </div>
    </form>
    <CategoryBudgets />
    </div>
  );
}
