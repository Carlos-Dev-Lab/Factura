import { query, request } from './client';
import type {
  Account,
  AccountInput,
  Alert,
  Backup,
  CalendarDay,
  Category,
  CategoryRule,
  FiscalReport,
  ImportItem,
  ImportMapping,
  ImportPreview,
  Invoice,
  InvoiceDraft,
  InvoiceFilter,
  InvoiceInput,
  MonthSummary,
  NotificationSettings,
  PaymentMethod,
  ScheduledHistory,
  ScheduledInput,
  ScheduledPayment,
  Suggestion,
  Transaction,
  TransactionInput,
  TransactionKind,
  TransactionPage,
  Transfer,
  TransferInput,
  TrashItem,
  User,
  YearReport,
} from './types';

/** Respuesta de un borrado: el elemento queda en la papelera y se puede "Deshacer". */
export interface Deleted {
  trash_id: number;
}

export const authApi = {
  config: () => request<{ registration_open: boolean; first_user: boolean; google_login: boolean }>('/auth/config'),
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) => request<User>('/auth/login', 'POST', { email, password }),
  register: (email: string, password: string, name: string) =>
    request<User>('/auth/register', 'POST', { email, password, name }),
  logout: () => request<void>('/auth/logout', 'POST'),
  logoutAll: () => request<void>('/auth/logout-all', 'POST'),
  updateProfile: (data: Partial<Omit<User, 'id' | 'email' | 'has_password' | 'google_email'>>) =>
    request<User>('/auth/me', 'PATCH', data),
  /** Sin contraseña actual solo si la cuenta todavía no tiene (creada con Google). */
  changePassword: (current_password: string | null, new_password: string) =>
    request<User>('/auth/password', 'POST', current_password === null ? { new_password } : { current_password, new_password }),
  googleLink: () => request<{ url: string }>('/auth/google/link', 'POST'),
  googleUnlink: () => request<void>('/auth/google', 'DELETE'),
};

/** Ingreso con Google: es una navegación (no un fetch), para que el navegador vaya y vuelva de Google. */
export const GOOGLE_LOGIN_URL = '/api/v1/auth/google/start';

export const categoriesApi = {
  list: () => request<Category[]>('/categories'),
  create: (data: Omit<Category, 'id' | 'monthly_budget'> & { monthly_budget?: number | null }) =>
    request<Category>('/categories', 'POST', data),
  update: (id: number, data: Partial<Pick<Category, 'name' | 'color' | 'monthly_budget'>>) =>
    request<Category>(`/categories/${id}`, 'PATCH', data),
  remove: (id: number) => request<Deleted>(`/categories/${id}`, 'DELETE'),
  suggest: (kind: TransactionKind, text: string, ruc = '') =>
    request<Suggestion>(`/categories/suggest${query({ kind, text, ruc })}`),
  rules: () => request<CategoryRule[]>('/categories/rules'),
  createRule: (data: { match: 'ruc' | 'contains'; pattern: string; category_id: number }) =>
    request<CategoryRule>('/categories/rules', 'POST', data),
  removeRule: (id: number) => request<void>(`/categories/rules/${id}`, 'DELETE'),
};

export interface TransactionFilters {
  start?: string;
  end?: string;
  kind?: TransactionKind;
  q?: string;
  limit?: number;
  account_id?: number;
  category_id?: number;
}

export const transactionsApi = {
  list: (f: TransactionFilters) => request<TransactionPage>(`/transactions${query({ ...f })}`),
  create: (data: TransactionInput) => request<Transaction>('/transactions', 'POST', data),
  update: (id: number, data: Partial<TransactionInput>) => request<Transaction>(`/transactions/${id}`, 'PATCH', data),
  remove: (id: number) => request<Deleted>(`/transactions/${id}`, 'DELETE'),
};

export interface PayOptions {
  method: PaymentMethod;
  paid_on?: string | null;
  account_id?: number | null;
}

export const invoicesApi = {
  list: (status?: InvoiceFilter, q?: string) => request<Invoice[]>(`/invoices${query({ status, q })}`),
  analyze: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<InvoiceDraft>('/invoices/analyze', 'POST', fd);
  },
  discardUpload: (fileKey: string) => request<void>(`/invoices/uploads/${fileKey}`, 'DELETE'),
  create: (
    data: InvoiceInput & {
      file_key: string | null;
      already_paid: boolean;
      account_id: number | null;
      allow_duplicate: boolean;
    },
  ) => request<Invoice>('/invoices', 'POST', data),
  update: (id: number, data: InvoiceInput) => request<Invoice>(`/invoices/${id}`, 'PATCH', data),
  pay: (id: number, opts: PayOptions = { method: 'transfer' }) => request<Invoice>(`/invoices/${id}/pay`, 'POST', opts),
  unpay: (id: number) => request<Invoice>(`/invoices/${id}/unpay`, 'POST'),
  remove: (id: number) => request<Deleted>(`/invoices/${id}`, 'DELETE'),
  fileUrl: (id: number) => `/api/v1/invoices/${id}/file`,
};

export const scheduledApi = {
  list: () => request<ScheduledPayment[]>('/scheduled-payments'),
  create: (data: ScheduledInput) => request<ScheduledPayment>('/scheduled-payments', 'POST', data),
  update: (id: number, data: Partial<ScheduledInput>) =>
    request<ScheduledPayment>(`/scheduled-payments/${id}`, 'PATCH', data),
  remove: (id: number) => request<Deleted>(`/scheduled-payments/${id}`, 'DELETE'),
  history: (id: number) => request<ScheduledHistory>(`/scheduled-payments/${id}/history`),
  pay: (id: number, month: string, opts: PayOptions & { amount?: number } = { method: 'transfer' }) =>
    request<Transaction>(`/scheduled-payments/${id}/pay`, 'POST', { month, ...opts }),
};

export const accountsApi = {
  list: () => request<Account[]>('/accounts'),
  create: (data: AccountInput) => request<Account>('/accounts', 'POST', data),
  update: (id: number, data: Partial<AccountInput> & { archived?: boolean }) =>
    request<Account>(`/accounts/${id}`, 'PATCH', data),
  remove: (id: number) => request<void>(`/accounts/${id}`, 'DELETE'),
  transfers: (f: { start?: string; end?: string; account_id?: number } = {}) =>
    request<Transfer[]>(`/accounts/transfers${query({ ...f })}`),
  transfer: (data: TransferInput) => request<Transfer>('/accounts/transfers', 'POST', data),
  removeTransfer: (id: number) => request<void>(`/accounts/transfers/${id}`, 'DELETE'),
};

export const reportsApi = {
  summary: (month: string) => request<MonthSummary>(`/reports/summary${query({ month })}`),
  calendar: (month: string) => request<{ month: string; days: CalendarDay[] }>(`/reports/calendar${query({ month })}`),
  year: (year: number) => request<YearReport>(`/reports/year${query({ year })}`),
  fiscal: (month: string) => request<FiscalReport>(`/reports/fiscal${query({ month })}`),
  fiscalCsvUrl: (month: string) => `/api/v1/reports/fiscal.csv${query({ month })}`,
  fiscalZipUrl: (month: string) => `/api/v1/reports/fiscal.zip${query({ month })}`,
  exportUrl: (month?: string) => `/api/v1/reports/export.csv${query({ month })}`,
  fullExportUrl: () => '/api/v1/export/full.zip',
};

export const notificationsApi = {
  alerts: () => request<Alert[]>('/alerts'),
  settings: () => request<NotificationSettings>('/notifications/settings'),
  updateSettings: (
    data: Partial<Pick<NotificationSettings, 'notifications_enabled' | 'notify_hour' | 'notify_days_before' | 'email_enabled'>>,
  ) =>
    request<NotificationSettings>('/notifications/settings', 'PATCH', data),
  pushKey: () => request<{ public_key: string }>('/notifications/push/key'),
  subscribe: (sub: PushSubscriptionJSON, label: string) =>
    request<void>('/notifications/push', 'POST', { endpoint: sub.endpoint, keys: sub.keys, label }),
  unsubscribe: (endpoint: string) => request<void>('/notifications/push/remove', 'POST', { endpoint }),
  linkTelegram: () => request<{ url: string; code: string; expires_at: string }>('/notifications/telegram', 'POST'),
  unlinkTelegram: () => request<void>('/notifications/telegram', 'DELETE'),
  emailStart: (address: string) => request<{ verified: boolean }>('/notifications/email', 'POST', { address }),
  emailConfirm: (code: string) => request<NotificationSettings>('/notifications/email/confirm', 'POST', { code }),
  emailRemove: () => request<void>('/notifications/email', 'DELETE'),
  test: () =>
    request<{ push_sent: number; telegram_sent: boolean; email_sent: boolean }>('/notifications/test', 'POST'),
};

export const dataApi = {
  trash: () => request<TrashItem[]>('/trash'),
  restore: (id: number) => request<{ entity: string; id: number }>(`/trash/${id}/restore`, 'POST'),
  removeFromTrash: (id: number) => request<void>(`/trash/${id}`, 'DELETE'),
  emptyTrash: () => request<void>('/trash', 'DELETE'),
  backups: () => request<Backup[]>('/system/backups'),
  importPreview: (file: File, mapping?: ImportMapping) => {
    const fd = new FormData();
    fd.append('file', file);
    if (mapping) fd.append('mapping', JSON.stringify(mapping));
    return request<ImportPreview>('/imports/preview', 'POST', fd);
  },
  importCommit: (account_id: number | null, items: ImportItem[]) =>
    request<{ created: number; total: number }>('/imports/commit', 'POST', { account_id, items }),
};
