import { scheduledApi } from '../../api/endpoints';
import { Switch } from '../../components/fields';
import { Icon } from '../../components/Icon';
import { Loading } from '../../components/Loading';
import { useDialogs } from '../../context/DialogsContext';
import { useFinancialMutation, useScheduled, useUser } from '../../hooks/queries';
import { formatMoney, monthLabel, tint } from '../../lib/format';
import { SectionHeader } from './SectionHeader';

export function ScheduledSection() {
  const { currency } = useUser();
  const { openScheduled } = useDialogs();
  const scheduled = useScheduled();
  const toggle = useFinancialMutation(({ id, active }: { id: number; active: boolean }) =>
    scheduledApi.update(id, { active }),
  );

  const items = scheduled.data ?? [];
  const active = items.filter((s) => s.active);
  const monthly = active.filter((s) => s.kind === 'expense').reduce((sum, s) => sum + s.amount, 0);
  const incomes = active.filter((s) => s.kind === 'income').reduce((sum, s) => sum + s.amount, 0);

  return (
    <section className="card">
      <SectionHeader
        title="Pagos y cobros fijos"
        description="Alquiler, servicios, cuotas o el sueldo: lo que se repite cada mes. Aparecen en el calendario, en próximos pagos y en la proyección del mes."
        action={
          <div className="row-actions">
            <button className="btn" onClick={() => openScheduled({ dayOfMonth: 1, kind: 'income' })}>
              + Cobro fijo
            </button>
            <button className="btn mint" onClick={() => openScheduled({ dayOfMonth: 1 })}>
              + Pago fijo
            </button>
          </div>
        }
      />
      {!scheduled.data ? (
        <Loading error={scheduled.error} />
      ) : items.length ? (
        <>
          <div className="stat-strip">
            <div>
              <small>Pagos por mes</small>
              <b>{formatMoney(monthly, currency)}</b>
            </div>
            {incomes > 0 && (
              <div>
                <small>Cobros por mes</small>
                <b className="pos">{formatMoney(incomes, currency)}</b>
              </div>
            )}
            <div>
              <small>Activos</small>
              <b>
                {active.length} de {items.length}
              </b>
            </div>
          </div>
          <ul className="list">
            {items.map((s) => (
              <li key={s.id} className={`item settings-row ${s.active ? '' : 'paused'}`}>
                <div className="datebox" aria-hidden="true">
                  <b>{s.day_of_month}</b>
                  <small>día</small>
                </div>
                <span className="body">
                  <b>{s.name}</b>
                  <span className="row-tags">
                    {s.category && (
                      <span className="tag" style={{ background: tint(s.category.color), color: s.category.color }}>
                        {s.category.name}
                      </span>
                    )}
                    {s.kind === 'income' && <span className="tag income-tag">Cobro</span>}
                    {s.variable_amount && <span className="tag">Monto variable</span>}
                    {s.installments && (
                      <span className="tag">
                        {s.installments} cuotas · hasta {monthLabel(s.end_month!).toLowerCase()}
                      </span>
                    )}
                    <span className={`amt ${s.kind === 'income' ? 'pos' : ''}`}>
                      {s.variable_amount && '≈ '}
                      {formatMoney(s.amount, currency)}
                    </span>
                  </span>
                </span>
                <span className="switch-wrap">
                  <small className="muted">{s.active ? 'Activo' : 'Pausado'}</small>
                  <Switch
                    checked={s.active}
                    label={`${s.active ? 'Pausar' : 'Activar'} ${s.name}`}
                    disabled={toggle.isPending}
                    onChange={(value) => toggle.mutate({ id: s.id, active: value })}
                  />
                </span>
                <button className="icon-btn" onClick={() => openScheduled({ payment: s })} aria-label={`Editar ${s.name}`}>
                  <Icon name="edit" size={16} />
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="empty">Todavía no cargaste pagos fijos. Agregá el primero con “+ Pago fijo”.</div>
      )}
    </section>
  );
}
