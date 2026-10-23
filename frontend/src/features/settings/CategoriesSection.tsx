import { useEffect, useRef, useState } from 'react';

import { categoriesApi } from '../../api/endpoints';
import type { Category, TransactionKind } from '../../api/types';
import { ConfirmDeleteButton, Field } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useCategories, useFinancialMutation } from '../../hooks/queries';
import { SectionHeader } from './SectionHeader';

const EXTRA_KEYS = ['categories'];
const PALETTE = ['#3EE6B0', '#8B7BFF', '#FFC24D', '#FF8A5B', '#FF6B9A', '#5AB8FF', '#C38BFF', '#4DD4E6'];
const GROUPS: { kind: TransactionKind; title: string; label: string }[] = [
  { kind: 'expense', title: 'Gastos', label: 'Gasto' },
  { kind: 'income', title: 'Ingresos', label: 'Ingreso' },
];

function CategoryRow({ category, fresh }: { category: Category; fresh: boolean }) {
  const ref = useRef<HTMLLIElement>(null);
  const [name, setName] = useState(category.name);
  const update = useFinancialMutation(
    (data: Partial<Pick<Category, 'name' | 'color'>>) => categoriesApi.update(category.id, data),
    'Categoría actualizada',
    EXTRA_KEYS,
  );
  const remove = useFinancialMutation(() => categoriesApi.remove(category.id), 'Categoría eliminada', EXTRA_KEYS);

  // Las nuevas quedan al final de la lista, que puede estar fuera de la vista.
  useEffect(() => {
    if (fresh) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [fresh]);

  const commitName = () => {
    const next = name.trim();
    if (!next) setName(category.name);
    else if (next !== category.name) update.mutate({ name: next }, { onError: () => setName(category.name) });
  };

  return (
    <li ref={ref} className={fresh ? 'cat-row fresh' : 'cat-row'}>
      <label className="swatch-pick" style={{ background: category.color }}>
        <span className="sr">Color de {category.name}</span>
        <input
          type="color"
          defaultValue={category.color}
          onBlur={(e) => {
            const next = e.target.value.toUpperCase();
            if (next !== category.color) update.mutate({ color: next });
          }}
        />
      </label>
      <input
        className="inline-input"
        aria-label={`Nombre de la categoría ${category.name}`}
        maxLength={40}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
      />
      <ConfirmDeleteButton compact label={`Eliminar ${category.name}`} onConfirm={() => remove.mutate(undefined)} />
    </li>
  );
}

interface NewCategoryDialogProps {
  initialKind: TransactionKind;
  onClose: () => void;
  onCreated: (category: Category) => void;
}

function NewCategoryDialog({ initialKind, onClose, onCreated }: NewCategoryDialogProps) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState(initialKind);
  const [color, setColor] = useState(PALETTE[5]!);
  const create = useFinancialMutation(categoriesApi.create, 'Categoría agregada', EXTRA_KEYS);

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(
      { name: trimmed, kind, color: color.toUpperCase() },
      {
        onSuccess: (category) => {
          onCreated(category);
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      title="Nueva categoría"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn mint" disabled={create.isPending || !name.trim()}>
            Agregar
          </button>
        </>
      }
    >
      <Field label="Nombre">
        <input
          required
          data-autofocus
          maxLength={40}
          placeholder="Ej. Mascotas"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <div className="f">
        <span>Tipo</span>
        <div className="seg cat-kind" role="radiogroup" aria-label="Tipo de categoría">
          {GROUPS.map((g) => (
            <button
              type="button"
              key={g.kind}
              role="radio"
              aria-checked={kind === g.kind}
              className={kind === g.kind ? 'on' : ''}
              onClick={() => setKind(g.kind)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>
      <div className="f">
        <span>Color</span>
        <div className="palette" role="radiogroup" aria-label="Color">
          {PALETTE.map((c) => (
            <button
              type="button"
              key={c}
              role="radio"
              aria-checked={color === c}
              aria-label={`Color ${c}`}
              className={color === c ? 'on' : ''}
              style={{ background: c }}
              onClick={() => setColor(c)}
            />
          ))}
          <label className="swatch-pick custom" style={{ background: PALETTE.includes(color) ? undefined : color }}>
            <span className="sr">Otro color</span>+
            <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
          </label>
        </div>
      </div>
    </Modal>
  );
}

export function CategoriesSection() {
  const { data: categories = [] } = useCategories();
  const [kind, setKind] = useState<TransactionKind>('expense');
  const [creating, setCreating] = useState(false);
  const [freshId, setFreshId] = useState<number | null>(null);
  const group = GROUPS.find((g) => g.kind === kind)!;
  const items = categories.filter((c) => c.kind === kind);

  // El resaltado de la categoría recién creada dura un instante.
  useEffect(() => {
    if (freshId === null) return;
    const timer = setTimeout(() => setFreshId(null), 1600);
    return () => clearTimeout(timer);
  }, [freshId]);

  return (
    <section className="card">
      <SectionHeader
        title="Categorías"
        description="Tocá un nombre para renombrarlo o el cuadro de color para cambiarlo. Al eliminar una categoría, sus movimientos quedan como “Sin categoría”."
        action={
          <button className="btn mint" onClick={() => setCreating(true)}>
            + Nueva categoría
          </button>
        }
      />
      <div className="seg cat-tabs" role="group" aria-label="Tipo de categoría">
        {GROUPS.map((g) => (
          <button
            key={g.kind}
            className={kind === g.kind ? 'on' : ''}
            aria-pressed={kind === g.kind}
            onClick={() => setKind(g.kind)}
          >
            {g.title} <span className="count">{categories.filter((c) => c.kind === g.kind).length}</span>
          </button>
        ))}
      </div>
      {items.length ? (
        // `key` reinicia el scroll al cambiar de pestaña.
        <ul key={kind} className="cat-list" aria-label={`Categorías de ${group.title.toLowerCase()}`}>
          {items.map((c) => (
            <CategoryRow key={`${c.id}-${c.name}-${c.color}`} category={c} fresh={c.id === freshId} />
          ))}
        </ul>
      ) : (
        <div className="empty">
          No tenés categorías de {group.title.toLowerCase()}. Agregá una con “+ Nueva categoría”.
        </div>
      )}
      {creating && (
        <NewCategoryDialog
          initialKind={kind}
          onClose={() => setCreating(false)}
          onCreated={(category) => {
            setKind(category.kind);
            setFreshId(category.id);
          }}
        />
      )}
    </section>
  );
}
