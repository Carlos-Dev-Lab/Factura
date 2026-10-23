import { useState } from 'react';

import { categoriesApi } from '../../api/endpoints';
import type { TransactionKind } from '../../api/types';
import { CategorySelect, ConfirmDeleteButton, Field } from '../../components/fields';
import { Loading } from '../../components/Loading';
import { useToast } from '../../context/ToastContext';
import { useFinancialMutation, useRules } from '../../hooks/queries';
import { tint } from '../../lib/format';
import { SectionHeader } from './SectionHeader';

const EXTRA = ['rules'];

export function RulesSection() {
  const toast = useToast();
  const rules = useRules();
  const [match, setMatch] = useState<'contains' | 'ruc'>('contains');
  const [pattern, setPattern] = useState('');
  const [kind, setKind] = useState<TransactionKind>('expense');
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const create = useFinancialMutation(categoriesApi.createRule, 'Regla guardada', EXTRA);
  const remove = useFinancialMutation(categoriesApi.removeRule, 'Regla eliminada', EXTRA);

  const items = rules.data ?? [];
  const manual = items.filter((r) => !r.learned);
  const learned = items.filter((r) => r.learned);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (pattern.trim().length < 2) return toast('Escribí al menos 2 letras');
    if (!categoryId) return toast('Elegí la categoría');
    create.mutate(
      { match, pattern: pattern.trim(), category_id: categoryId },
      { onSuccess: () => setPattern('') },
    );
  };

  const list = (title: string, rows: typeof items, hint: string) => (
    <div className="rule-group">
      <h3>{title}</h3>
      <p className="hint">{hint}</p>
      {rows.length ? (
        <ul className="list compact">
          {rows.map((r) => (
            <li key={r.id} className="item">
              <span className="body">
                <b>{r.match === 'ruc' ? `RUC ${r.pattern}` : `Contiene «${r.pattern}»`}</b>
                <small>
                  <span className="tag" style={{ background: tint(r.category.color), color: r.category.color }}>
                    {r.category.name}
                  </span>
                </small>
              </span>
              <ConfirmDeleteButton compact label={`Eliminar regla ${r.pattern}`} onConfirm={() => remove.mutate(r.id)} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">Ninguna todavía.</div>
      )}
    </div>
  );

  return (
    <div className="stack">
      <form className="card" onSubmit={submit}>
        <SectionHeader
          title="Reglas automáticas"
          description="Categorizan solos los movimientos, las facturas y los extractos importados. Las que creás aquí tienen prioridad sobre lo aprendido."
        />
        <div className="seg" role="radiogroup" aria-label="Tipo de regla">
          <button type="button" role="radio" aria-checked={match === 'contains'} className={match === 'contains' ? 'on' : ''} onClick={() => setMatch('contains')}>
            Texto en la descripción
          </button>
          <button type="button" role="radio" aria-checked={match === 'ruc'} className={match === 'ruc' ? 'on' : ''} onClick={() => setMatch('ruc')}>
            RUC del proveedor
          </button>
        </div>
        <div className="fgrid spaced">
          <Field label={match === 'ruc' ? 'RUC' : 'Si la descripción contiene'}>
            <input
              required
              maxLength={80}
              placeholder={match === 'ruc' ? '80009735-1' : 'Ej. Shell, Biggie, Netflix'}
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
            />
          </Field>
          <Field label="Tipo">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as TransactionKind);
                setCategoryId(null);
              }}
            >
              <option value="expense">Gasto</option>
              <option value="income">Ingreso</option>
            </select>
          </Field>
          <CategorySelect kind={kind} value={categoryId} onChange={setCategoryId} />
        </div>
        <button className="btn mint" disabled={create.isPending}>
          Agregar regla
        </button>
      </form>
      {!rules.data ? (
        <Loading error={rules.error} />
      ) : (
        <section className="card">
          {list('Tus reglas', manual, 'Se aplican primero.')}
          {list(
            'Aprendidas',
            learned,
            'Se crean solas cuando elegís una categoría para un proveedor o una descripción. Borrá las que no te sirvan.',
          )}
        </section>
      )}
    </div>
  );
}
