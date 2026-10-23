import { dataApi } from '../../api/endpoints';
import type { TrashItem } from '../../api/types';
import { ConfirmDeleteButton } from '../../components/fields';
import { Icon } from '../../components/Icon';
import { Loading } from '../../components/Loading';
import { useFinancialMutation, useTrash } from '../../hooks/queries';
import { SectionHeader } from './SectionHeader';

const ENTITY: Record<TrashItem['entity'], string> = {
  transaction: 'Movimiento',
  invoice: 'Factura',
  scheduled: 'Pago fijo',
  category: 'Categoría',
};
const KEEP_DAYS = 30;

function daysLeft(deletedAt: string): number {
  const elapsed = (Date.now() - new Date(deletedAt).getTime()) / 86_400_000;
  return Math.max(0, Math.ceil(KEEP_DAYS - elapsed));
}

export function TrashSection() {
  const trash = useTrash();
  const extra = ['categories', 'rules'];
  const restore = useFinancialMutation(dataApi.restore, 'Restaurado', extra);
  const remove = useFinancialMutation(dataApi.removeFromTrash, 'Eliminado definitivamente', extra);
  const empty = useFinancialMutation(dataApi.emptyTrash, 'Papelera vaciada', extra);
  const items = trash.data ?? [];

  return (
    <section className="card">
      <SectionHeader
        title="Papelera"
        description={`Lo que borrás queda aquí ${KEEP_DAYS} días por si te arrepentís. Al restaurar una factura vuelve con su archivo y su pago.`}
        action={
          items.length > 0 && <ConfirmDeleteButton label="Vaciar papelera" onConfirm={() => empty.mutate(undefined)} />
        }
      />
      {!trash.data ? (
        <Loading error={trash.error} />
      ) : items.length ? (
        <ul className="list">
          {items.map((item) => (
            <li key={item.id} className="item">
              <span className="body">
                <b>{item.label}</b>
                <small>
                  {ENTITY[item.entity]} · se borra en {daysLeft(item.deleted_at)} días
                </small>
              </span>
              <button className="btn small" disabled={restore.isPending} onClick={() => restore.mutate(item.id)}>
                <Icon name="restore" size={16} /> Restaurar
              </button>
              <ConfirmDeleteButton compact label={`Eliminar ${item.label}`} onConfirm={() => remove.mutate(item.id)} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">La papelera está vacía.</div>
      )}
    </section>
  );
}
