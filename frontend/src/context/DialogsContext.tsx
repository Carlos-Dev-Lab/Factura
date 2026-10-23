import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { invoicesApi } from '../api/endpoints';
import type { DueItem } from '../api/types';
import { AccountDialog, type AccountDialogState } from '../features/accounts/AccountDialog';
import { TransferDialog, type TransferDraft } from '../features/accounts/TransferDialog';
import { PayDialog } from '../features/dues/PayDialog';
import { InvoiceDialog, type InvoiceDialogState } from '../features/invoices/InvoiceDialog';
import { ScheduledDialog, type ScheduledDialogState } from '../features/scheduled/ScheduledDialog';
import { TransactionDialog, type TransactionDraft } from '../features/transactions/TransactionDialog';
import { takeSharedFile } from '../lib/pwa';
import { useMonth } from './MonthContext';
import { useToast } from './ToastContext';

interface Dialogs {
  openTransaction: (draft?: TransactionDraft) => void;
  openInvoice: (state: InvoiceDialogState) => void;
  openScheduled: (state: ScheduledDialogState) => void;
  /** Registrar el pago de una factura, un pago fijo o el resumen de una tarjeta. */
  openPay: (due: DueItem) => void;
  openTransfer: (draft?: TransferDraft) => void;
  openAccount: (state: AccountDialogState) => void;
  /** Abre el selector de archivos (o la cámara) y analiza la factura elegida. */
  pickInvoiceFile: (useCamera?: boolean) => void;
  analyzeInvoice: (file: File) => void;
}

type Active =
  | { type: 'transaction'; draft: TransactionDraft }
  | { type: 'invoice'; state: InvoiceDialogState }
  | { type: 'scheduled'; state: ScheduledDialogState }
  | { type: 'pay'; due: DueItem }
  | { type: 'transfer'; draft: TransferDraft }
  | { type: 'account'; state: AccountDialogState }
  | { type: 'analyzing'; previewUrl?: string; name: string }
  | null;

const DialogsContext = createContext<Dialogs | null>(null);

// PDF, fotos y el XML de la factura electrónica.
const INVOICE_ACCEPT = 'application/pdf,image/*,.xml,text/xml,application/xml';

export function DialogsProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<Active>(null);
  const { defaultDay } = useMonth();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<string>();

  const close = useCallback(() => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = undefined;
    setActive(null);
  }, []);

  const analyzeInvoice = useCallback(
    async (file: File) => {
      const previewUrl = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined;
      previewRef.current = previewUrl;
      setActive({ type: 'analyzing', previewUrl, name: file.name });
      try {
        const draft = await invoicesApi.analyze(file);
        setActive({ type: 'invoice', state: { mode: 'new', draft, previewUrl } });
      } catch (err) {
        toast((err as Error).message);
        close();
      }
    },
    [toast, close],
  );

  // Archivo compartido desde otra app (WhatsApp, correo...) con "Compartir → Factura".
  useEffect(() => {
    void takeSharedFile().then((file) => file && analyzeInvoice(file));
  }, [analyzeInvoice]);

  const value = useMemo<Dialogs>(
    () => ({
      openTransaction: (draft = {}) => setActive({ type: 'transaction', draft }),
      openInvoice: (state) => setActive({ type: 'invoice', state }),
      openScheduled: (state) => setActive({ type: 'scheduled', state }),
      // El resumen de una tarjeta se paga con una transferencia desde otra cuenta.
      openPay: (due) =>
        setActive(
          due.kind === 'card'
            ? { type: 'transfer', draft: { to_account_id: due.id, amount: due.amount, description: `Pago ${due.name}` } }
            : { type: 'pay', due },
        ),
      openTransfer: (draft = {}) => setActive({ type: 'transfer', draft }),
      openAccount: (state) => setActive({ type: 'account', state }),
      pickInvoiceFile: (useCamera = false) => (useCamera ? cameraRef : fileRef).current?.click(),
      analyzeInvoice: (file) => void analyzeInvoice(file),
    }),
    [analyzeInvoice],
  );

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) void analyzeInvoice(file);
  };

  return (
    <DialogsContext.Provider value={value}>
      {children}
      <input ref={fileRef} type="file" accept={INVOICE_ACCEPT} hidden onChange={onFile} />
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={onFile} />
      {active?.type === 'transaction' && (
        <TransactionDialog initial={active.draft} defaultDate={defaultDay} onClose={close} />
      )}
      {active?.type === 'invoice' && <InvoiceDialog state={active.state} onClose={close} />}
      {active?.type === 'scheduled' && <ScheduledDialog state={active.state} onClose={close} />}
      {active?.type === 'pay' && <PayDialog due={active.due} onClose={close} />}
      {active?.type === 'transfer' && <TransferDialog draft={active.draft} onClose={close} />}
      {active?.type === 'account' && <AccountDialog state={active.state} onClose={close} />}
      {active?.type === 'analyzing' && (
        <div className="analyzing" role="alert" aria-busy="true">
          <div className="modal-card">
            <h2>Analizando factura…</h2>
            <div className="preview scan">
              {active.previewUrl ? <img src={active.previewUrl} alt="" /> : <p className="muted">{active.name}</p>}
            </div>
            <p className="muted">Leyendo el documento. Las fotos pueden tardar unos segundos.</p>
          </div>
        </div>
      )}
    </DialogsContext.Provider>
  );
}

export function useDialogs(): Dialogs {
  const ctx = useContext(DialogsContext);
  if (!ctx) throw new Error('useDialogs debe usarse dentro de DialogsProvider');
  return ctx;
}
