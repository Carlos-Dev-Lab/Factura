import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import {
  accountsApi,
  authApi,
  categoriesApi,
  dataApi,
  invoicesApi,
  notificationsApi,
  reportsApi,
  scheduledApi,
  transactionsApi,
  type TransactionFilters,
} from '../api/endpoints';
import type { InvoiceFilter, User } from '../api/types';
import { useToast } from '../context/ToastContext';

export const keys = {
  me: ['me'] as const,
  categories: ['categories'] as const,
  rules: ['rules'] as const,
  summary: (month: string) => ['summary', month] as const,
  calendar: (month: string) => ['calendar', month] as const,
  transactions: (f: TransactionFilters) => ['transactions', f] as const,
  invoices: (status?: InvoiceFilter, q?: string) => ['invoices', status, q] as const,
  scheduled: ['scheduled'] as const,
  history: (id: number) => ['history', id] as const,
  accounts: ['accounts'] as const,
  transfers: (f: object) => ['transfers', f] as const,
  alerts: ['alerts'] as const,
  year: (year: number) => ['year', year] as const,
  fiscal: (month: string) => ['fiscal', month] as const,
  trash: ['trash'] as const,
  notifications: ['notifications'] as const,
  backups: ['backups'] as const,
};

// Datos que cambian cuando se registra o modifica cualquier movimiento.
const FINANCIAL_KEYS = [
  'summary',
  'calendar',
  'transactions',
  'invoices',
  'scheduled',
  'history',
  'accounts',
  'transfers',
  'alerts',
  'year',
  'fiscal',
  'trash',
];

function refreshFinancial(qc: QueryClient, extra: string[] = []) {
  return Promise.all([...FINANCIAL_KEYS, ...extra].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: authApi.me, retry: false, staleTime: Infinity });

/** Usuario autenticado. Solo usar dentro de rutas protegidas. */
export function useUser(): User {
  const { data } = useMe();
  if (!data) throw new Error('useUser requiere una sesión iniciada');
  return data;
}

export const useCategories = () =>
  useQuery({ queryKey: keys.categories, queryFn: categoriesApi.list, staleTime: 5 * 60_000 });

export const useRules = () => useQuery({ queryKey: keys.rules, queryFn: categoriesApi.rules });

export const useSummary = (month: string) =>
  useQuery({ queryKey: keys.summary(month), queryFn: () => reportsApi.summary(month) });

export const useCalendar = (month: string) =>
  useQuery({ queryKey: keys.calendar(month), queryFn: () => reportsApi.calendar(month) });

export const useTransactions = (filters: TransactionFilters) =>
  useQuery({ queryKey: keys.transactions(filters), queryFn: () => transactionsApi.list(filters) });

export const useInvoices = (status?: InvoiceFilter, q?: string) =>
  useQuery({ queryKey: keys.invoices(status, q), queryFn: () => invoicesApi.list(status, q) });

export const useScheduled = () => useQuery({ queryKey: keys.scheduled, queryFn: scheduledApi.list });

export const usePaymentHistory = (id: number | null) =>
  useQuery({ queryKey: keys.history(id ?? 0), queryFn: () => scheduledApi.history(id!), enabled: id !== null });

export const useAccounts = () => useQuery({ queryKey: keys.accounts, queryFn: accountsApi.list });

/** Cuentas que se pueden usar (no archivadas). La primera es la cuenta por defecto. */
export function useActiveAccounts() {
  const q = useAccounts();
  return { ...q, data: q.data?.filter((a) => !a.archived) };
}

export const useTransfers = (f: { start?: string; end?: string; account_id?: number } = {}) =>
  useQuery({ queryKey: keys.transfers(f), queryFn: () => accountsApi.transfers(f) });

// Los avisos se revisan cada pocos minutos aunque no se toque nada (vencen con el paso del día).
export const useAlerts = () =>
  useQuery({ queryKey: keys.alerts, queryFn: notificationsApi.alerts, refetchInterval: 5 * 60_000 });

export const useYearReport = (year: number) =>
  useQuery({ queryKey: keys.year(year), queryFn: () => reportsApi.year(year) });

export const useFiscalReport = (month: string) =>
  useQuery({ queryKey: keys.fiscal(month), queryFn: () => reportsApi.fiscal(month) });

export const useTrash = () => useQuery({ queryKey: keys.trash, queryFn: dataApi.trash });

export const useNotificationSettings = () =>
  useQuery({ queryKey: keys.notifications, queryFn: notificationsApi.settings });

export const useBackups = () => useQuery({ queryKey: keys.backups, queryFn: dataApi.backups });

const isDeleted = (r: unknown): r is { trash_id: number } =>
  typeof r === 'object' && r !== null && typeof (r as { trash_id?: unknown }).trash_id === 'number';

/**
 * Mutación que, al terminar bien, refresca los datos financieros y muestra un aviso.
 * Si fue un borrado, el aviso ofrece "Deshacer" (restaura desde la papelera).
 * Los errores se muestran siempre como aviso.
 */
export function useFinancialMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  successMessage?: string,
  extraKeys: string[] = [],
) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await refreshFinancial(qc, extraKeys);
      if (!successMessage) return;
      if (isDeleted(result)) {
        toast(successMessage, {
          label: 'Deshacer',
          onClick: () => {
            dataApi
              .restore(result.trash_id)
              .then(() => refreshFinancial(qc, ['categories', 'rules', ...extraKeys]))
              .then(() => toast('Restaurado'))
              .catch((err: Error) => toast(err.message));
          },
        });
      } else {
        toast(successMessage);
      }
    },
    onError: (err: Error) => toast(err.message),
  });
}
