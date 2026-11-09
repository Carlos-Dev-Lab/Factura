import { useEffect, useRef, useState } from 'react';

import { categoriesApi } from '../../api/endpoints';
import type { Category, TransactionKind } from '../../api/types';
import { ConfirmDeleteButton, Field } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useCategories, useFinancialMutation } from '../../hooks/queries';
import { SectionHeader } from './SectionHeader';

const EXTRA_KEYS = ['categories'];
const PALETTE = ['#3EE6B0', '#8B7BFF', '#FFC24D', '#FF8A5B', '#FF6B9A', '#5AB8FF', '#C38BFF', '#4DD4E6'];
const usedColor = (color: string, categories: Category[], exclude?: number) =>
  categories.some((c) => c.id !== exclude && c.color.toUpperCase() === color.toUpperCase());

function availableColor(categories: Category[]): string {
  const fromPalette = PALETTE.find((color) => !usedColor(color, categories));
  if (fromPalette) return fromPalette;
  // Genera colores adicionales si ya se usó toda la paleta.
  for (let i = 0; i < 360; i++) {
    const hue = (i * 137.508) % 360;
    const a = 0.65 * Math.min(0.62, 1 - 0.62);
    const component = (n: number) => {
      const k = (n + hue / 30) % 12;
      return Math.round(255 * (0.62 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))).toString(16).padStart(2, '0');
    };
    const color = `#${component(0)}${component(8)}${component(4)}`.toUpperCase();
    if (!usedColor(color, categories)) return color;
  }
  return '#FFFFFF';
}
const GROUPS: { kind: TransactionKind; title: string; label: string }[] = [
  { kind: 'expense', title: 'Gastos', label: 'Gasto' },
  { kind: 'income', title: 'Ingresos', label: 'Ingreso' },
];

function CategoryRow({ category, fresh, categories, allowRepeated, onMove, busy, dragging, offset, onDragStart, onDragMove, onDragEnd, onDragCancel }: {
  category: Category; fresh: boolean; categories: Category[]; allowRepeated: boolean;
  onMove: (direction: number) => void; busy: boolean; dragging: boolean; offset: number;
  onDragStart: (row: HTMLLIElement, y: number) => void; onDragMove: (y: number) => void; onDragEnd: () => void; onDragCancel: () => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const [name, setName] = useState(category.name);
  const [colorError, setColorError] = useState('');
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
    <li ref={ref} className={`cat-row${fresh ? ' fresh' : ''}${dragging ? ' dragging' : ''}`}
      style={offset ? { transform: `translateY(${offset}px)` } : undefined}>
      <button type="button" className="cat-drag" aria-label={`Mover ${category.name}`} title="Arrastrá para ordenar; también podés usar las flechas del teclado" disabled={busy}
        onPointerDown={(e) => {
          if (e.button !== 0 || !ref.current) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          onDragStart(ref.current, e.clientY);
        }}
        onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) onDragMove(e.clientY); }}
        onPointerUp={onDragEnd} onLostPointerCapture={onDragCancel}
        onKeyDown={(e) => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); onMove(e.key === 'ArrowUp' ? -1 : 1); } }}>⠿</button>
      <label className="swatch-pick" style={{ background: category.color }}>
        <span className="sr">Color de {category.name}</span>
        <input
          type="color"
          defaultValue={category.color}
          onBlur={(e) => {
            const next = e.target.value.toUpperCase();
            if (next === category.color.toUpperCase()) return;
            if (!allowRepeated && usedColor(next, categories, category.id)) {
              e.target.value = category.color;
              setColorError('Este color ya está en uso. Elegí otro o habilitá colores repetidos.');
              return;
            }
            setColorError('');
            update.mutate({ color: next }, { onError: () => { e.target.value = category.color; } });
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
      {colorError && <span className="cat-color-error" role="alert">{colorError}</span>}
      <ConfirmDeleteButton compact label={`Eliminar ${category.name}`} onConfirm={() => remove.mutate(undefined)} />
    </li>
  );
}

interface NewCategoryDialogProps {
  initialKind: TransactionKind;
  categories: Category[];
  allowRepeated: boolean;
  onClose: () => void;
  onCreated: (category: Category) => void;
}

function NewCategoryDialog({ initialKind, categories, allowRepeated, onClose, onCreated }: NewCategoryDialogProps) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState(initialKind);
  const [color, setColor] = useState(() => availableColor(categories));
  const repeated = usedColor(color, categories);
  const create = useFinancialMutation(categoriesApi.create, 'Categoría agregada', EXTRA_KEYS);

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed || (!allowRepeated && repeated)) return;
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
          <button className="btn mint" disabled={create.isPending || !name.trim() || (!allowRepeated && repeated)}>
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
              disabled={!allowRepeated && usedColor(c, categories)}
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
        {!allowRepeated && repeated && <span role="alert" className="hint">Este color ya está en uso. Elegí otro.</span>}
        {!allowRepeated && <span className="hint">Los colores ya utilizados están deshabilitados.</span>}
      </div>
    </Modal>
  );
}

export function CategoriesSection() {
  const { data: categories = [] } = useCategories();
  const [kind, setKind] = useState<TransactionKind>('expense');
  const [creating, setCreating] = useState(false);
  const [freshId, setFreshId] = useState<number | null>(null);
  const [allowRepeated, setAllowRepeated] = useState(false);
  const [dragPreview, setDragPreview] = useState<{ from: number; to: number; offset: number; space: number } | null>(null);
  const drag = useRef<{ from: number; to: number; startY: number; startScroll: number; row: HTMLLIElement; space: number } | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [pendingOrder, setPendingOrder] = useState<{ kind: TransactionKind; ids: number[] } | null>(null);
  const reorder = useFinancialMutation(categoriesApi.reorder, 'Orden actualizado', EXTRA_KEYS);
  const group = GROUPS.find((g) => g.kind === kind)!;
  const savedItems = categories.filter((c) => c.kind === kind);
  const items = pendingOrder?.kind === kind
    ? pendingOrder.ids.flatMap((id) => savedItems.filter((item) => item.id === id))
    : savedItems;

  const move = (index: number, direction: number) => {
    const ids = items.map((item) => item.id);
    const target = index + direction;
    if (target < 0 || target >= ids.length || reorder.isPending) return;
    [ids[index], ids[target]] = [ids[target]!, ids[index]!];
    reorder.mutate({ kind, ids });
  };

  const cancelDrag = () => {
    drag.current = null;
    setDragPreview(null);
  };

  const finishDrag = () => {
    const current = drag.current;
    cancelDrag();
    if (!current || current.from === current.to || reorder.isPending) return;
    const ids = items.map((item) => item.id);
    ids.splice(current.to, 0, ids.splice(current.from, 1)[0]!);
    setPendingOrder({ kind, ids });
    reorder.mutate({ kind, ids }, { onSettled: () => setPendingOrder(null) });
  };

  const startDrag = (from: number, row: HTMLLIElement, y: number) => {
    const list = listRef.current;
    if (!list) return;
    const space = row.offsetHeight + parseFloat(getComputedStyle(list).rowGap);
    drag.current = { from, to: from, row, startY: y, startScroll: list.scrollTop, space };
    setDragPreview({ from, to: from, offset: 0, space });
  };

  const updateDrag = (y: number) => {
    const current = drag.current;
    const list = listRef.current;
    if (!current || !list) return;
    const bounds = list.getBoundingClientRect();
    if (y < bounds.top + 30) list.scrollTop -= 12;
    else if (y > bounds.bottom - 30) list.scrollTop += 12;
    const offset = y - current.startY + list.scrollTop - current.startScroll;
    const center = current.row.offsetTop + current.row.offsetHeight / 2 + offset;
    // offsetTop reflects the layout before the visual shifts, so the target stays stable.
    current.to = Array.from(list.children).filter((row) =>
      row instanceof HTMLElement && row !== current.row && center > row.offsetTop + row.offsetHeight / 2,
    ).length;
    setDragPreview({ from: current.from, to: current.to, offset, space: current.space });
  };

  const rowOffset = (index: number) => {
    if (!dragPreview) return 0;
    const { from, to, offset, space } = dragPreview;
    if (index === from) return offset;
    if (index > from && index <= to) return -space;
    if (index < from && index >= to) return space;
    return 0;
  };

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
        description="Mantené presionado el ícono de puntos y arrastrá la categoría hasta la posición deseada. También podés cambiar su nombre o color."
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
      <div className="cat-tools">
        <button type="button" className="btn" disabled={reorder.isPending || items.length < 2} onClick={() => reorder.mutate({ kind, ids: [...items].sort((a, b) => a.name.localeCompare(b.name, 'es', { sensitivity: 'base' })).map((item) => item.id) })}>Ordenar A–Z</button>
        <label className="cat-repeat"><input type="checkbox" checked={allowRepeated} onChange={(e) => setAllowRepeated(e.target.checked)} /> Permitir colores repetidos</label>
      </div>
      {items.length ? (
        // `key` reinicia el scroll al cambiar de pestaña.
        <ul ref={listRef} key={kind} className={`cat-list${dragPreview ? ' sorting' : ''}`} aria-label={`Categorías de ${group.title.toLowerCase()}`}>
          {items.map((c, index) => (
            <CategoryRow key={`${c.id}-${c.name}-${c.color}`} category={c} fresh={c.id === freshId} categories={categories} allowRepeated={allowRepeated} busy={reorder.isPending} dragging={dragPreview?.from === index}
              offset={rowOffset(index)} onMove={(direction) => move(index, direction)} onDragStart={(row, y) => startDrag(index, row, y)}
              onDragMove={updateDrag} onDragEnd={finishDrag} onDragCancel={cancelDrag} />
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
          categories={categories}
          allowRepeated={allowRepeated}
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
