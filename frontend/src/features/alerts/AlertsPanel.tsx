import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import type { Alert } from '../../api/types';
import { Icon } from '../../components/Icon';
import { useAlerts } from '../../hooks/queries';

const LEVEL_LABEL = { danger: 'Urgente', warn: 'Atención', info: 'Aviso' } as const;

function AlertItem({ alert, onNavigate }: { alert: Alert; onNavigate?: () => void }) {
  const navigate = useNavigate();
  return (
    <li>
      <button
        type="button"
        className={`alert-item ${alert.level}`}
        onClick={() => {
          onNavigate?.();
          navigate(alert.link);
        }}
      >
        <span className="dot" aria-hidden="true" />
        <span className="body">
          <b>{alert.title}</b>
          <small>
            <span className="sr">{LEVEL_LABEL[alert.level]}: </span>
            {alert.body}
          </small>
        </span>
        <Icon name="right" size={16} />
      </button>
    </li>
  );
}

/** Campana del encabezado con los avisos de hoy (vencimientos y presupuestos). */
export function AlertsBell() {
  const { data: alerts = [] } = useAlerts();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const urgent = alerts.filter((a) => a.level !== 'info').length;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="bell-wrap" ref={ref}>
      <button
        className={`icon-btn bell ${urgent ? 'has' : ''}`}
        aria-label={alerts.length ? `Avisos: ${alerts.length}` : 'Avisos: ninguno'}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" size={19} />
        {alerts.length > 0 && <span className="badge">{alerts.length > 9 ? '9+' : alerts.length}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Avisos">
          <div className="popover-head">
            <b>Avisos</b>
            <Link to="/ajustes?seccion=avisos" className="link" onClick={() => setOpen(false)}>
              Configurar
            </Link>
          </div>
          {alerts.length ? (
            <ul className="alert-list">
              {alerts.map((a) => (
                <AlertItem key={a.key} alert={a} onNavigate={() => setOpen(false)} />
              ))}
            </ul>
          ) : (
            <div className="empty">Todo al día: nada vence pronto ni hay presupuestos al límite.</div>
          )}
        </div>
      )}
    </div>
  );
}

/** Avisos urgentes arriba del panel (vencido, vence hoy, presupuesto superado). */
export function AlertsStrip() {
  const { data: alerts = [] } = useAlerts();
  const important = alerts.filter((a) => a.level !== 'info').slice(0, 3);
  if (!important.length) return null;
  return (
    <section className="alerts-strip" aria-label="Avisos importantes">
      <ul className="alert-list">
        {important.map((a) => (
          <AlertItem key={a.key} alert={a} />
        ))}
      </ul>
    </section>
  );
}
