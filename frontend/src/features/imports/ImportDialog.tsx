import { useMemo, useState } from 'react';

import { dataApi } from '../../api/endpoints';
import type { ImportMapping, ImportPreview, ImportRow } from '../../api/types';
import { AccountSelect, Field } from '../../components/fields';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useActiveAccounts, useCategories, useFinancialMutation, useUser } from '../../hooks/queries';
import { formatDate, formatMoney } from '../../lib/format';

type AmountMode = 'single' | 'split';

function ColumnSelect({
  label,
  columns,
  value,
  onChange,
  optional = false,
}: {
  label: string;
  columns: string[];
  value: number | null;
  onChange: (v: number | null) => void;
  optional?: boolean;
}) {
  return (
    <Field label={label}>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}>
        {optional && <option value="">(ninguna)</option>}
        {!optional && value === null && <option value="">Elegí una columna</option>}
        {columns.map((c, i) => (
          <option key={i} value={i}>
            {c}
          </option>
        ))}
      </select>
    </Field>
  );
}

/** Importar un extracto bancario (CSV o Excel) en dos pasos: revisar y confirmar. */
export function ImportDialog({ onClose, accountId }: { onClose: () => void; accountId?: number | null }) {
  const { currency } = useUser();
  const toast = useToast();
  const { data: categories = [] } = useCategories();
  const { data: accounts = [] } = useActiveAccounts();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [mode, setMode] = useState<AmountMode>('split');
  const [rows, setRows] = useState<(ImportRow & { selected: boolean })[]>([]);
  const [account, setAccount] = useState<number | null>(accountId ?? null);
  const [busy, setBusy] = useState(false);
  const [editingColumns, setEditingColumns] = useState(false);

  const read = async (f: File, m?: ImportMapping) => {
    setBusy(true);
    try {
      const p = await dataApi.importPreview(f, m);
      setPreview(p);
      const used = p.mapping ?? m ?? null;
      setMapping(
        used ?? { date: 0, description: null, amount: null, debit: null, credit: null, header_row: 0, day_first: true },
      );
      setMode(used && used.amount !== null ? 'single' : 'split');
      setEditingColumns(!p.mapping);
      setRows(p.rows.map((r) => ({ ...r, selected: !r.duplicate && !r.error })));
      if (account === null) setAccount(accounts.find((a) => a.type === 'bank')?.id ?? accounts[0]?.id ?? null);
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const commit = useFinancialMutation(
    () =>
      dataApi.importCommit(
        account,
        rows
          .filter((r) => r.selected && r.date && r.amount)
          .map((r) => ({
            date: r.date!,
            description: r.description,
            amount: r.amount!,
            kind: r.kind,
            category_id: r.category_id,
          })),
      ),
  );

  const chosen = useMemo(() => rows.filter((r) => r.selected && r.date && r.amount), [rows]);
  const totals = useMemo(
    () => ({
      expense: chosen.filter((r) => r.kind === 'expense').reduce((s, r) => s + (r.amount ?? 0), 0),
      income: chosen.filter((r) => r.kind === 'income').reduce((s, r) => s + (r.amount ?? 0), 0),
    }),
    [chosen],
  );
  const update = (line: number, patch: Partial<ImportRow & { selected: boolean }>) =>
    setRows((rs) => rs.map((r) => (r.line === line ? { ...r, ...patch } : r)));

  const setMap = <K extends keyof ImportMapping>(k: K, v: ImportMapping[K]) =>
    setMapping((m) => (m ? { ...m, [k]: v } : m));

  const applyColumns = () => {
    if (!file || !mapping) return;
    const m = mode === 'single' ? { ...mapping, debit: null, credit: null } : { ...mapping, amount: null };
    void read(file, m);
  };

  const submit = () => {
    if (!preview) return;
    if (!chosen.length) return toast('No hay filas seleccionadas para importar');
    commit.mutate(undefined, {
      onSuccess: (r) => {
        toast(`Se importaron ${r.created} movimientos`);
        onClose();
      },
    });
  };

  return (
    <Modal
      title="Importar extracto bancario"
      wide
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn mint" disabled={!chosen.length || commit.isPending || busy}>
            Importar {chosen.length || ''} movimientos
          </button>
        </>
      }
    >
      <p className="muted">
        Descargá el extracto desde la web de tu banco en CSV o Excel (.xlsx). Se detectan las columnas, se marcan los
        movimientos que ya cargaste y se sugiere la categoría.
      </p>
      <Field label="Archivo">
        <input
          type="file"
          accept=".csv,.txt,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            if (f) void read(f);
          }}
        />
      </Field>
      {busy && <div className="found mid">Leyendo el archivo…</div>}
      {preview && mapping && (
        <>
          {editingColumns ? (
            <div className="import-columns">
              <p className="hint">
                {preview.mapping ? 'Columnas elegidas:' : 'No se reconocieron los encabezados. Elegí qué columna es cada dato:'}
              </p>
              <div className="fgrid">
                <ColumnSelect label="Fecha" columns={preview.columns} value={mapping.date} onChange={(v) => setMap('date', v ?? 0)} />
                <ColumnSelect
                  label="Descripción"
                  columns={preview.columns}
                  value={mapping.description}
                  onChange={(v) => setMap('description', v)}
                  optional
                />
              </div>
              <div className="seg" role="radiogroup" aria-label="Formato del monto">
                <button type="button" className={mode === 'split' ? 'on' : ''} onClick={() => setMode('split')}>
                  Débito y crédito separados
                </button>
                <button type="button" className={mode === 'single' ? 'on' : ''} onClick={() => setMode('single')}>
                  Una columna con signo
                </button>
              </div>
              <div className="fgrid">
                {mode === 'single' ? (
                  <ColumnSelect label="Monto (negativo = gasto)" columns={preview.columns} value={mapping.amount} onChange={(v) => setMap('amount', v)} />
                ) : (
                  <>
                    <ColumnSelect label="Débito (gastos)" columns={preview.columns} value={mapping.debit} onChange={(v) => setMap('debit', v)} optional />
                    <ColumnSelect label="Crédito (ingresos)" columns={preview.columns} value={mapping.credit} onChange={(v) => setMap('credit', v)} optional />
                  </>
                )}
                <Field label="Fila de encabezados" hint="Número de fila (la primera es 1).">
                  <input
                    type="number"
                    min={1}
                    value={mapping.header_row + 1}
                    onChange={(e) => setMap('header_row', Math.max(0, Number(e.target.value) - 1))}
                  />
                </Field>
              </div>
              <label className="check">
                <input type="checkbox" checked={!mapping.day_first} onChange={(e) => setMap('day_first', !e.target.checked)} />
                Las fechas vienen como mes/día (formato de EE. UU.)
              </label>
              <button type="button" className="btn" disabled={busy} onClick={applyColumns}>
                Volver a leer con estas columnas
              </button>
            </div>
          ) : (
            <button type="button" className="btn small" onClick={() => setEditingColumns(true)}>
              Cambiar columnas
            </button>
          )}
          {rows.length > 0 && (
            <>
              <div className="fgrid">
                <AccountSelect label="Cuenta del extracto" value={account} onChange={setAccount} />
                <div className="import-totals">
                  <span>
                    Gastos <b className="neg">{formatMoney(totals.expense, currency)}</b>
                  </span>
                  <span>
                    Ingresos <b className="pos">{formatMoney(totals.income, currency)}</b>
                  </span>
                </div>
              </div>
              <div className="table-wrap import-table">
                <table>
                  <thead>
                    <tr>
                      <th>
                        <span className="sr">Importar</span>
                      </th>
                      <th>Fecha</th>
                      <th>Descripción</th>
                      <th className="r">Monto</th>
                      <th>Categoría</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.line} className={r.duplicate || r.error ? 'dim' : ''}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Importar fila ${r.line}`}
                            checked={r.selected}
                            disabled={!!r.error}
                            onChange={(e) => update(r.line, { selected: e.target.checked })}
                          />
                        </td>
                        <td>{r.date ? formatDate(r.date) : '—'}</td>
                        <td>
                          {r.description || <span className="muted">Sin descripción</span>}
                          {r.duplicate && (
                            <small className="tag dup" title="Ya hay un movimiento con la misma fecha y monto. Marcalo si igual querés importarlo.">
                              Posible repetido
                            </small>
                          )}
                          {r.error && <small className="tag err">{r.error}</small>}
                        </td>
                        <td className={`r num ${r.kind === 'expense' ? 'neg' : 'pos'}`}>
                          {r.amount ? formatMoney(r.kind === 'expense' ? -r.amount : r.amount, currency, { sign: true }) : '—'}
                        </td>
                        <td>
                          <select
                            aria-label={`Categoría de la fila ${r.line}`}
                            value={r.category_id ?? ''}
                            onChange={(e) => update(r.line, { category_id: e.target.value ? Number(e.target.value) : null })}
                          >
                            <option value="">Sin categoría</option>
                            {categories
                              .filter((c) => c.kind === r.kind)
                              .map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name}
                                </option>
                              ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.skipped > 0 && (
                <p className="hint">Se omitieron {preview.skipped} filas sin fecha ni monto (títulos, saldos o totales).</p>
              )}
            </>
          )}
          {!rows.length && !editingColumns && <div className="empty">No se encontraron movimientos en el archivo.</div>}
        </>
      )}
    </Modal>
  );
}
