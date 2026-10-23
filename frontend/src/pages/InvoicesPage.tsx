import { useDeferredValue, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { invoicesApi, reportsApi } from '../api/endpoints';
import type { DueItem, Invoice, InvoiceFilter } from '../api/types';
import { Field } from '../components/fields';
import { Icon } from '../components/Icon';
import { Loading } from '../components/Loading';
import { useDialogs } from '../context/DialogsContext';
import { useFiscalReport, useInvoices, useUser } from '../hooks/queries';
import { formatDate, formatMoney, monthLabel, monthOf, relativeDay, shiftMonth, todayIso } from '../lib/format';

const FILTERS: { value: InvoiceFilter | undefined; label: string }[] = [
  { value: undefined, label: 'Todas' },
  { value: 'pending', label: 'Pendientes' },
  { value: 'overdue', label: 'Vencidas' },
  { value: 'paid', label: 'Pagadas' },
];

function statusOf(i: Invoice): { cls: string; label: string } {
  if (i.status === 'paid') return { cls: 'paid', label: 'Pagada' };
  return i.overdue ? { cls: 'overdue', label: 'Vencida' } : { cls: 'pending', label: 'Pendiente' };
}

const asDue = (i: Invoice): DueItem => ({
  kind: 'invoice',
  id: i.id,
  name: i.supplier || 'Factura',
  amount: i.total,
  date: i.due_date ?? i.issue_date,
  state: i.overdue ? 'overdue' : 'pending',
  direction: 'out',
  detail: null,
  estimated: false,
});

function DropZone() {
  const { pickInvoiceFile, analyzeInvoice, openInvoice } = useDialogs();
  const [over, setOver] = useState(false);
  return (
    <div
      className={`drop ${over ? 'over' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const file = e.dataTransfer.files[0];
        if (file) analyzeInvoice(file);
      }}
    >
      <div className="paper" aria-hidden="true">
        <i style={{ width: '70%' }} />
        <i style={{ width: '50%' }} />
        <i />
        <i style={{ width: '80%' }} />
        <i className="m" />
      </div>
      <div className="txt">
        <strong>Analizar una factura</strong>
        <span className="muted">
          Arrastrá un PDF, una foto o el XML de la factura electrónica. Con factura electrónica (QR, CDC o XML) los
          datos son exactos; con fotos se leen proveedor, RUC, número, fechas, total e IVA.
        </span>
      </div>
      <div className="btns">
        <button className="btn mint" onClick={() => pickInvoiceFile()}>
          Elegir archivo
        </button>
        <button className="btn" onClick={() => pickInvoiceFile(true)}>
          <Icon name="camera" size={18} /> Sacar foto
        </button>
        <button className="btn" onClick={() => openInvoice({ mode: 'new' })}>
          Cargar a mano
        </button>
      </div>
    </div>
  );
}

function InvoiceTable({ items }: { items: Invoice[] }) {
  const { currency } = useUser();
  const { openInvoice, openPay } = useDialogs();
  if (!items.length) return <div className="empty">No hay facturas aquí todavía. Subí una para empezar.</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Proveedor</th>
            <th>N.º / RUC</th>
            <th>Vence</th>
            <th className="r">Monto</th>
            <th>Estado</th>
            <th className="r">
              <span className="sr">Acciones</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => {
            const st = statusOf(i);
            const when = i.due_date ?? i.issue_date;
            return (
              <tr key={i.id}>
                <td>
                  <b>{i.supplier || 'Sin nombre'}</b>
                  {i.cdc && (
                    <span className="tag fe" title="Factura electrónica">
                      FE
                    </span>
                  )}
                  <br />
                  <small className="muted">{i.category?.name ?? ''}</small>
                </td>
                <td className="muted">
                  {i.number || '—'}
                  <br />
                  <small>{i.ruc}</small>
                </td>
                <td>
                  {formatDate(when)}
                  <br />
                  <small className="muted">{i.due_date && i.status === 'pending' ? relativeDay(i.due_date) : ''}</small>
                </td>
                <td className="r num">{formatMoney(i.total, currency)}</td>
                <td>
                  <span className={`status ${st.cls}`}>{st.label}</span>
                </td>
                <td className="r">
                  <div className="row-actions">
                    {i.status === 'pending' && (
                      <button className="btn small mint" onClick={() => openPay(asDue(i))}>
                        Pagar
                      </button>
                    )}
                    {i.has_file && (
                      <a
                        className="btn small"
                        href={invoicesApi.fileUrl(i.id)}
                        target={i.file_type === 'xml' ? undefined : '_blank'}
                        rel="noopener noreferrer"
                      >
                        {i.file_type === 'xml' ? 'XML' : 'Ver'}
                      </a>
                    )}
                    <button
                      className="icon-btn"
                      onClick={() => openInvoice({ mode: 'edit', invoice: i })}
                      aria-label={`Editar factura de ${i.supplier || 'sin nombre'}`}
                    >
                      <Icon name="edit" size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FiscalSection() {
  const { currency } = useUser();
  const { openInvoice } = useDialogs();
  // Por defecto el mes anterior: es el que se declara.
  const [month, setMonth] = useState(() => shiftMonth(monthOf(todayIso()), -1));
  const report = useFiscalReport(month);
  const money = (v: number) => formatMoney(v, currency);

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Para el contador</h2>
          <p className="muted">Compras del mes por fecha de emisión, con IVA 10 %, 5 %, exentas y gastos deducibles de IRP.</p>
        </div>
        <Field label="Mes">
          <input type="month" value={month} max={monthOf(todayIso())} onChange={(e) => e.target.value && setMonth(e.target.value)} />
        </Field>
      </div>
      {!report.data ? (
        <Loading error={report.error} />
      ) : (
        <>
          <div className="mini-stats three">
            <div>
              <small>Total compras</small>
              <b>{money(report.data.total)}</b>
              <small>{report.data.rows.length} facturas</small>
            </div>
            <div>
              <small>IVA 10 %</small>
              <b>{money(report.data.iva10)}</b>
              <small>Gravado {money(report.data.taxed10)}</small>
            </div>
            <div>
              <small>IVA 5 %</small>
              <b>{money(report.data.iva5)}</b>
              <small>Gravado {money(report.data.taxed5)}</small>
            </div>
            <div>
              <small>Exentas</small>
              <b>{money(report.data.exempt)}</b>
            </div>
            <div>
              <small>Deducible IRP</small>
              <b className="pos">{money(report.data.irp_total)}</b>
            </div>
          </div>
          {report.data.missing_iva > 0 && (
            <div className="found mid">
              <Icon name="alert" size={18} />
              {report.data.missing_iva === 1
                ? '1 factura no tiene el IVA cargado.'
                : `${report.data.missing_iva} facturas no tienen el IVA cargado.`}{' '}
              Revisalas antes de mandar el reporte.
            </div>
          )}
          {report.data.rows.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Proveedor / RUC</th>
                    <th className="r">IVA 10 %</th>
                    <th className="r">IVA 5 %</th>
                    <th className="r">Total</th>
                    <th>IRP</th>
                  </tr>
                </thead>
                <tbody>
                  {report.data.rows.map((r) => {
                    const missing = r.total > 0 && !(r.iva10 || r.iva5 || r.exempt);
                    return (
                      <tr key={r.invoice_id}>
                        <td>{formatDate(r.issue_date)}</td>
                        <td>
                          <b>{r.supplier || 'Sin nombre'}</b>
                          <br />
                          <small className="muted">
                            {r.ruc || 'Sin RUC'} · {r.number || 'sin número'}
                          </small>
                        </td>
                        <td className="r num">{money(r.iva10)}</td>
                        <td className="r num">{money(r.iva5)}</td>
                        <td className="r num">{money(r.total)}</td>
                        <td>
                          {missing ? (
                            <button
                              className="btn small"
                              onClick={() =>
                                invoicesApi
                                  .list(undefined, r.number || r.supplier)
                                  .then((list) => {
                                    const inv = list.find((x) => x.id === r.invoice_id);
                                    if (inv) openInvoice({ mode: 'edit', invoice: inv });
                                  })
                              }
                            >
                              Completar IVA
                            </button>
                          ) : r.irp_deductible ? (
                            'Sí'
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="row-actions start spaced">
            <a className="btn" href={reportsApi.fiscalCsvUrl(month)}>
              <Icon name="download" size={18} /> Planilla (CSV)
            </a>
            <a className="btn mint" href={reportsApi.fiscalZipUrl(month)}>
              <Icon name="download" size={18} /> Paquete con archivos (ZIP)
            </a>
          </div>
          <p className="hint spaced">
            El ZIP trae la planilla de {monthLabel(month).toLowerCase()} y los archivos de las facturas, listos para
            mandar. Confirmá con tu contador el formato que usa para cargarlas en el sistema de la SET.
          </p>
        </>
      )}
    </div>
  );
}

export function InvoicesPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('vista') === 'contador' ? 'contador' : 'facturas';
  const [filter, setFilter] = useState<InvoiceFilter | undefined>();
  const [search, setSearch] = useState('');
  const q = useDeferredValue(search.trim());
  const invoices = useInvoices(filter, q || undefined);

  return (
    <div className="stack">
      <div className="seg" role="tablist" aria-label="Vista">
        <button role="tab" aria-selected={tab === 'facturas'} className={tab === 'facturas' ? 'on' : ''} onClick={() => setParams({}, { replace: true })}>
          Facturas
        </button>
        <button
          role="tab"
          aria-selected={tab === 'contador'}
          className={tab === 'contador' ? 'on' : ''}
          onClick={() => setParams({ vista: 'contador' }, { replace: true })}
        >
          Para el contador
        </button>
      </div>
      {tab === 'contador' ? (
        <FiscalSection />
      ) : (
        <>
          <DropZone />
          <div className="card">
            <div className="toolbar">
              <div className="seg" role="group" aria-label="Filtrar facturas">
                {FILTERS.map((f) => (
                  <button
                    key={f.label}
                    className={filter === f.value ? 'on' : ''}
                    aria-pressed={filter === f.value}
                    onClick={() => setFilter(f.value)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <label className="search">
                <Icon name="search" size={18} />
                <span className="sr">Buscar facturas</span>
                <input
                  type="search"
                  placeholder="Proveedor, RUC, número o CDC…"
                  maxLength={80}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
            </div>
            {invoices.data ? <InvoiceTable items={invoices.data} /> : <Loading error={invoices.error} />}
          </div>
        </>
      )}
    </div>
  );
}
