import { useState } from 'react';

import { reportsApi } from '../../api/endpoints';
import { Field } from '../../components/fields';
import { Icon } from '../../components/Icon';
import { useBackups } from '../../hooks/queries';
import { monthLabel, monthOf, todayIso } from '../../lib/format';
import { SectionHeader } from './SectionHeader';

function size(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function BackupsCard() {
  const { data: backups } = useBackups();
  const latest = backups?.[0];
  const hoursAgo = latest ? (Date.now() - new Date(latest.created_at).getTime()) / 3_600_000 : null;
  const stale = hoursAgo !== null && hoursAgo > 36;

  return (
    <section className="card">
      <SectionHeader
        title="Respaldos automáticos"
        description="Todos los días se guarda una copia de la base de datos y de los archivos de las facturas en la carpeta backups del servidor."
      />
      {!backups ? null : backups.length === 0 ? (
        <div className="found mid">
          <Icon name="alert" size={18} />
          Todavía no hay respaldos. Revisá los registros del contenedor “db” (ver README).
        </div>
      ) : (
        <>
          <div className={`found ${stale ? 'mid' : 'ok'}`}>
            <Icon name={stale ? 'alert' : 'check'} size={18} />
            Último respaldo: {new Date(latest!.created_at).toLocaleString('es-PY', { dateStyle: 'medium', timeStyle: 'short' })}
            {stale && ' · hace más de un día, revisá el servicio de respaldos'}
          </div>
          <ul className="list compact spaced">
            {backups.slice(0, 6).map((b) => (
              <li key={b.name} className="item">
                <span className="body">
                  <b>{b.name}</b>
                  <small>{new Date(b.created_at).toLocaleString('es-PY')}</small>
                </span>
                <span className="muted small">{size(b.size)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="hint spaced">
        Para restaurar un respaldo seguí los pasos de la sección “Respaldos” del README. Guardá también una copia fuera
        de esta computadora (un disco externo o la nube).
      </p>
    </section>
  );
}

export function DataSection() {
  const [month, setMonth] = useState(monthOf(todayIso()));
  return (
    <div className="stack">
      <section className="card">
        <SectionHeader
          title="Exportar datos"
          description="Descargá tus movimientos en CSV para abrirlos en Excel, Google Sheets u otra planilla."
        />
        <div className="export-grid">
          <div className="export-box">
            <Field label="Mes a exportar">
              <input type="month" value={month} max={monthOf(todayIso())} onChange={(e) => setMonth(e.target.value)} />
            </Field>
            <a className={`btn mint ${month ? '' : 'disabled'}`} href={month ? reportsApi.exportUrl(month) : undefined}>
              Descargar {month ? monthLabel(month).toLowerCase() : 'mes'}
            </a>
          </div>
          <div className="export-box">
            <p className="soft">Todos los movimientos registrados, desde el primero hasta hoy.</p>
            <a className="btn" href={reportsApi.exportUrl()}>
              Descargar todo
            </a>
          </div>
          <div className="export-box">
            <p className="soft">
              Copia completa de tu cuenta: movimientos, facturas con sus archivos, cuentas, pagos fijos y reglas (ZIP).
            </p>
            <a className="btn" href={reportsApi.fullExportUrl()}>
              <Icon name="download" size={18} /> Descargar mis datos
            </a>
          </div>
        </div>
      </section>
      <BackupsCard />
    </div>
  );
}
