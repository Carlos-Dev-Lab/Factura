import { useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { categoriesApi, invoicesApi } from '../../api/endpoints';
import type { Invoice, InvoiceDraft, InvoiceInput, ReadMethod } from '../../api/types';
import { AccountSelect, CategorySelect, ConfirmDeleteButton, Field, MoneyInput } from '../../components/fields';
import { Icon } from '../../components/Icon';
import { Modal } from '../../components/Modal';
import { useToast } from '../../context/ToastContext';
import { useActiveAccounts, useFinancialMutation, useUser } from '../../hooks/queries';
import { formatMoney, todayIso } from '../../lib/format';
import { rucIsValid } from '../../lib/ruc';

export type InvoiceDialogState =
  | { mode: 'edit'; invoice: Invoice }
  | { mode: 'new'; draft?: InvoiceDraft; previewUrl?: string };

const EMPTY: InvoiceInput = {
  supplier: '',
  ruc: '',
  number: '',
  stamp: '',
  cdc: null,
  issue_date: null,
  due_date: null,
  total: 0,
  iva10: 0,
  iva5: 0,
  exempt: 0,
  irp_deductible: false,
  category_id: null,
  notes: '',
};

function initialForm(state: InvoiceDialogState): InvoiceInput {
  if (state.mode === 'edit') {
    const { invoice: i } = state;
    return {
      supplier: i.supplier,
      ruc: i.ruc,
      number: i.number,
      stamp: i.stamp,
      cdc: i.cdc,
      issue_date: i.issue_date,
      due_date: i.due_date,
      total: i.total,
      iva10: i.iva10,
      iva5: i.iva5,
      exempt: i.exempt,
      irp_deductible: i.irp_deductible,
      category_id: i.category?.id ?? null,
      notes: i.notes,
    };
  }
  const d = state.draft;
  return {
    ...EMPTY,
    supplier: d?.supplier ?? '',
    ruc: d?.ruc ?? '',
    number: d?.number ?? '',
    stamp: d?.stamp ?? '',
    cdc: d?.cdc ?? null,
    issue_date: d?.issue_date ?? todayIso(),
    due_date: d?.due_date ?? null,
    total: d?.total ?? 0,
    iva10: d?.iva10 ?? 0,
    iva5: d?.iva5 ?? 0,
    exempt: d?.exempt ?? 0,
    category_id: d?.category_id ?? null,
  };
}

const EXACT: Partial<Record<ReadMethod, string>> = {
  xml: 'Datos exactos del XML de la factura electrónica. Revisá y guardá.',
  qr: 'Datos exactos del código QR de la factura electrónica. Revisá y guardá.',
  cdc: 'Se leyó el CDC: RUC, número y fecha son exactos. Revisá el resto.',
};

function AnalysisBanner({ draft }: { draft: InvoiceDraft }) {
  const exact = EXACT[draft.method];
  const pct = Math.round(draft.confidence * 100);
  const [cls, text] = exact
    ? ['ok', exact]
    : pct >= 60
      ? ['ok', 'Datos detectados. Revisá y guardá.']
      : pct > 0
        ? ['mid', 'Se detectaron algunos datos. Completá lo que falta.']
        : ['mid', 'No se pudo leer el documento. Completá los datos a mano.'];
  return (
    <div className={`found ${cls}`}>
      <Icon name="check" size={18} stroke={2.4} />
      {text}
    </div>
  );
}

export function InvoiceDialog({ state, onClose }: { state: InvoiceDialogState; onClose: () => void }) {
  const { currency } = useUser();
  const toast = useToast();
  const { data: accounts } = useActiveAccounts();
  const [form, setForm] = useState<InvoiceInput>(() => initialForm(state));
  const [alreadyPaid, setAlreadyPaid] = useState(false);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [allowDuplicate, setAllowDuplicate] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const [categoryTouched, setCategoryTouched] = useState(state.mode === 'edit' || !!state.draft?.category_id);
  const set = <K extends keyof InvoiceInput>(k: K, v: InvoiceInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const draft = state.mode === 'new' ? state.draft : undefined;
  const editing = state.mode === 'edit' ? state.invoice : undefined;
  const duplicate = draft?.duplicate_of;
  const rucValid = form.ruc ? rucIsValid(form.ruc) : null;
  const hasTaxes = form.iva10 > 0 || form.iva5 > 0 || form.exempt > 0 || form.irp_deductible;
  // La clave reinicia los campos de IVA cuando se completan con los botones rápidos.
  const [taxKey, setTaxKey] = useState(0);

  useEffect(() => {
    if (accountId === null && accounts?.length) setAccountId(accounts.find((a) => a.type !== 'card')?.id ?? null);
  }, [accounts, accountId]);

  const save = useFinancialMutation(
    (data: InvoiceInput) =>
      editing
        ? invoicesApi.update(editing.id, data)
        : invoicesApi.create({
            ...data,
            file_key: draft?.file_key ?? null,
            already_paid: alreadyPaid,
            account_id: alreadyPaid ? accountId : null,
            allow_duplicate: allowDuplicate,
          }),
    'Factura guardada',
  );
  const remove = useFinancialMutation(() => invoicesApi.remove(editing!.id), 'Factura eliminada');
  const unpay = useFinancialMutation(() => invoicesApi.unpay(editing!.id), 'Factura marcada como pendiente');

  const cancel = () => {
    if (draft) void invoicesApi.discardUpload(draft.file_key);
    onClose();
  };

  // Con el RUC cargado a mano se sugiere la categoría que usaste antes para ese proveedor.
  const suggestByRuc = () => {
    if (categoryTouched || rucValid === false || form.ruc.length < 5) return;
    categoriesApi
      .suggest('expense', form.supplier, form.ruc)
      .then((s) => s.category_id && !categoryTouched && set('category_id', s.category_id))
      .catch(() => undefined);
  };

  const quickTax = (mode: '10' | '5' | 'exenta') => {
    const t = form.total;
    setForm((f) => ({
      ...f,
      iva10: mode === '10' ? Math.round(t / 11) : 0,
      iva5: mode === '5' ? Math.round(t / 21) : 0,
      exempt: mode === 'exenta' ? t : 0,
    }));
    setTaxKey((k) => k + 1);
  };

  const submit = () => {
    if (form.total <= 0) return toast('Ingresá un monto mayor a cero');
    if (duplicate && !allowDuplicate) return toast('Esta factura ya está cargada. Marcá «Guardar igual» si es otra.');
    save.mutate(form, {
      onSuccess: onClose,
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409 && err.message.includes('Guardar igual')) {
          setDuplicateError(err.message);
        }
      },
    });
  };

  return (
    <Modal
      title={editing ? 'Editar factura' : draft ? 'Revisar factura' : 'Nueva factura'}
      onClose={cancel}
      onSubmit={submit}
      footer={
        <>
          {editing && <ConfirmDeleteButton onConfirm={() => remove.mutate(undefined, { onSuccess: onClose })} />}
          {editing?.status === 'paid' && (
            <button type="button" className="btn" onClick={() => unpay.mutate(undefined, { onSuccess: onClose })}>
              Marcar pendiente
            </button>
          )}
          <button type="button" className="btn" onClick={cancel}>
            Cancelar
          </button>
          <button className="btn mint" disabled={save.isPending}>
            Guardar factura
          </button>
        </>
      }
    >
      {state.mode === 'new' && state.previewUrl && (
        <div className="preview">
          <img src={state.previewUrl} alt="Factura subida" />
        </div>
      )}
      {draft && <AnalysisBanner draft={draft} />}
      {(duplicate || duplicateError) && (
        <div className="found bad" role="alert">
          <Icon name="alert" size={18} stroke={2.4} />
          <span>
            {duplicate
              ? `Ya cargaste esta factura: ${duplicate.label} (${duplicate.status === 'paid' ? 'pagada' : 'pendiente'}).`
              : duplicateError}
          </span>
        </div>
      )}
      {(duplicate || duplicateError) && !editing && (
        <label className="check">
          <input type="checkbox" checked={allowDuplicate} onChange={(e) => setAllowDuplicate(e.target.checked)} />
          Guardar igual (es otra factura)
        </label>
      )}
      <div className="fgrid">
        <Field label="Proveedor">
          <input required maxLength={120} value={form.supplier} onChange={(e) => set('supplier', e.target.value)} />
        </Field>
        <Field
          label="RUC"
          hint={rucValid === false ? 'El dígito verificador no coincide: revisá el RUC.' : undefined}
        >
          <input
            maxLength={20}
            inputMode="numeric"
            placeholder="80009735-1"
            aria-invalid={rucValid === false}
            value={form.ruc}
            onChange={(e) => set('ruc', e.target.value)}
            onBlur={suggestByRuc}
          />
        </Field>
        <Field label="N.º de factura">
          <input
            maxLength={40}
            placeholder="001-001-0000001"
            value={form.number}
            onChange={(e) => set('number', e.target.value)}
          />
        </Field>
        <Field label="Timbrado">
          <input maxLength={20} inputMode="numeric" value={form.stamp} onChange={(e) => set('stamp', e.target.value)} />
        </Field>
        <Field label="Fecha de emisión">
          <input
            type="date"
            value={form.issue_date ?? ''}
            onChange={(e) => set('issue_date', e.target.value || null)}
          />
        </Field>
        <Field label="Vencimiento">
          <input type="date" value={form.due_date ?? ''} onChange={(e) => set('due_date', e.target.value || null)} />
        </Field>
        <MoneyInput label="Monto total" value={form.total} onChange={(v) => set('total', v)} />
        <CategorySelect
          kind="expense"
          value={form.category_id}
          onChange={(v) => {
            setCategoryTouched(true);
            set('category_id', v);
          }}
        />
      </div>
      {form.cdc && (
        <p className="hint mono" title="Código de control de la factura electrónica">
          CDC {form.cdc.replace(/(\d{4})(?=\d)/g, '$1 ')}
        </p>
      )}
      <details className="fiscal" open={hasTaxes}>
        <summary>
          Datos para el contador <span className="muted">(IVA y deducción de IRP)</span>
        </summary>
        <div className="fiscal-body">
          <div className="row-actions start">
            <span className="muted small">Completar:</span>
            <button type="button" className="btn small" disabled={!form.total} onClick={() => quickTax('10')}>
              Todo 10 %
            </button>
            <button type="button" className="btn small" disabled={!form.total} onClick={() => quickTax('5')}>
              Todo 5 %
            </button>
            <button type="button" className="btn small" disabled={!form.total} onClick={() => quickTax('exenta')}>
              Exenta
            </button>
          </div>
          <div className="fgrid three" key={taxKey}>
            <MoneyInput label="IVA 10 %" value={form.iva10} onChange={(v) => set('iva10', v)} />
            <MoneyInput label="IVA 5 %" value={form.iva5} onChange={(v) => set('iva5', v)} />
            <MoneyInput label="Exentas" value={form.exempt} onChange={(v) => set('exempt', v)} />
          </div>
          {form.iva10 + form.iva5 + form.exempt > form.total && form.total > 0 && (
            <p className="hint neg">El IVA y las exentas no pueden superar el total ({formatMoney(form.total, currency)}).</p>
          )}
          <label className="check">
            <input
              type="checkbox"
              checked={form.irp_deductible}
              onChange={(e) => set('irp_deductible', e.target.checked)}
            />
            Gasto deducible del IRP (salud, educación, vivienda, etc.)
          </label>
        </div>
      </details>
      <Field label="Notas">
        <textarea maxLength={2000} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
      </Field>
      {!editing && (
        <>
          <label className="check">
            <input type="checkbox" checked={alreadyPaid} onChange={(e) => setAlreadyPaid(e.target.checked)} />
            Ya está pagada (registrar el gasto)
          </label>
          {alreadyPaid && <AccountSelect label="Pagada con" value={accountId} onChange={setAccountId} />}
        </>
      )}
      {draft?.raw_text && (
        <details className="raw">
          <summary>Ver texto leído ({draft.method === 'xml' ? 'XML' : draft.method === 'pdf' ? 'PDF' : 'OCR'})</summary>
          <pre>{draft.raw_text}</pre>
        </details>
      )}
    </Modal>
  );
}
