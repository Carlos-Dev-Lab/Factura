// Tipos que reflejan los esquemas de la API (backend/app/schemas).

export type TransactionKind = 'expense' | 'income';
export type PaymentMethod = 'cash' | 'debit' | 'credit' | 'transfer' | 'qr';
export type InvoiceFilter = 'pending' | 'overdue' | 'paid';
export type DueState = 'pending' | 'overdue' | 'paid';
export type Currency = 'PYG' | 'USD' | 'ARS' | 'BRL' | 'EUR';
export type AccountType = 'cash' | 'bank' | 'card' | 'wallet';

export interface User {
  id: number;
  email: string;
  name: string;
  currency: Currency;
  monthly_budget: number;
  daily_limit: number;
  /** false en una cuenta creada con Google que todavía no eligió contraseña. */
  has_password: boolean;
  /** Cuenta de Google vinculada (puede ser distinta del email de la cuenta). */
  google_email: string | null;
}

export interface Category {
  id: number;
  name: string;
  color: string;
  kind: TransactionKind;
  monthly_budget: number | null;
}

type CategoryRef = Pick<Category, 'id' | 'name' | 'color'>;

interface AccountRef {
  id: number;
  name: string;
  color: string;
  type: AccountType;
}

interface CardStatus {
  last_closing: string;
  next_closing: string;
  due_date: string;
  next_due_date: string;
  statement_amount: number;
  current_period: number;
  debt: number;
  available: number | null;
}

export interface Account extends AccountRef {
  opening_balance: number;
  archived: boolean;
  closing_day: number | null;
  due_day: number | null;
  credit_limit: number | null;
  balance: number;
  movement_count: number;
  card: CardStatus | null;
}

export interface AccountInput {
  name: string;
  type: AccountType;
  color: string;
  opening_balance: number;
  closing_day: number | null;
  due_day: number | null;
  credit_limit: number | null;
}

export interface Transfer {
  id: number;
  from_account: AccountRef;
  to_account: AccountRef;
  amount: number;
  date: string;
  description: string;
}

export interface TransferInput {
  from_account_id: number;
  to_account_id: number;
  amount: number;
  date: string;
  description: string;
}

export interface Transaction {
  id: number;
  kind: TransactionKind;
  amount: number;
  date: string;
  description: string;
  method: PaymentMethod;
  category: CategoryRef | null;
  account: AccountRef | null;
  invoice_id: number | null;
  scheduled_payment_id: number | null;
}

export interface TransactionInput {
  kind: TransactionKind;
  amount: number;
  date: string;
  description: string;
  method: PaymentMethod;
  category_id: number | null;
  account_id: number | null;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  expense_total: number;
  income_total: number;
}

export interface Invoice {
  id: number;
  supplier: string;
  ruc: string;
  number: string;
  stamp: string;
  cdc: string | null;
  issue_date: string | null;
  due_date: string | null;
  total: number;
  iva10: number;
  iva5: number;
  exempt: number;
  irp_deductible: boolean;
  category: CategoryRef | null;
  status: 'pending' | 'paid';
  notes: string;
  paid_on: string | null;
  has_file: boolean;
  file_type: string | null;
  overdue: boolean;
}

export interface InvoiceInput {
  supplier: string;
  ruc: string;
  number: string;
  stamp: string;
  cdc: string | null;
  issue_date: string | null;
  due_date: string | null;
  total: number;
  iva10: number;
  iva5: number;
  exempt: number;
  irp_deductible: boolean;
  category_id: number | null;
  notes: string;
}

export type ReadMethod = 'xml' | 'qr' | 'cdc' | 'pdf' | 'ocr' | 'none';

export interface InvoiceDraft {
  file_key: string;
  supplier: string | null;
  ruc: string | null;
  number: string | null;
  stamp: string | null;
  cdc: string | null;
  issue_date: string | null;
  due_date: string | null;
  total: number | null;
  iva10: number | null;
  iva5: number | null;
  exempt: number | null;
  category_id: number | null;
  confidence: number;
  method: ReadMethod;
  ruc_valid: boolean | null;
  duplicate_of: { id: number; label: string; status: 'pending' | 'paid' } | null;
  raw_text: string;
}

export interface ScheduledPayment {
  id: number;
  name: string;
  kind: TransactionKind;
  amount: number;
  variable_amount: boolean;
  day_of_month: number;
  start_month: string;
  end_month: string | null;
  installments: number | null;
  category: CategoryRef | null;
  account_id: number | null;
  active: boolean;
}

export interface ScheduledInput {
  name: string;
  kind: TransactionKind;
  amount: number;
  variable_amount: boolean;
  day_of_month: number;
  start_month: string;
  end_month: string | null;
  category_id: number | null;
  account_id: number | null;
  active: boolean;
}

export interface ScheduledHistory {
  items: { transaction_id: number; date: string; amount: number }[];
  last_amount: number | null;
  average: number | null;
}

export interface DueItem {
  kind: 'invoice' | 'scheduled' | 'card';
  id: number;
  name: string;
  amount: number;
  date: string | null;
  state: DueState;
  direction: 'in' | 'out';
  detail: string | null;
  estimated: boolean;
}

export interface BudgetStatus {
  category_id: number;
  name: string;
  color: string;
  budget: number;
  spent: number;
  pct: number;
  state: 'ok' | 'warn' | 'over';
}

interface Projection {
  pending_income: number;
  pending_expense: number;
  projected_balance: number;
  days_left: number;
  daily_allowance: number | null;
  budget_daily_allowance: number | null;
}

export interface MonthSummary {
  month: string;
  income: number;
  expense: number;
  balance: number;
  budget: number;
  budget_used_pct: number | null;
  previous_expense: number;
  expense_change_pct: number | null;
  due_total: number;
  overdue_count: number;
  transaction_count: number;
  today_expense: number;
  daily_limit: number;
  by_category: { category_id: number | null; name: string; color: string; amount: number }[];
  budgets: BudgetStatus[];
  projection: Projection;
  daily: { date: string; expense: number; income: number }[];
  upcoming: DueItem[];
}

export interface CalendarDay {
  date: string;
  expense: number;
  income: number;
  dues: DueItem[];
}

export interface YearReport {
  year: number;
  months: { month: string; income: number; expense: number; balance: number }[];
  categories: { category_id: number | null; name: string; color: string; total: number; months: number[] }[];
  income: number;
  expense: number;
  balance: number;
  average_expense: number;
  months_counted: number;
}

interface FiscalRow {
  invoice_id: number;
  issue_date: string | null;
  supplier: string;
  ruc: string;
  stamp: string;
  number: string;
  cdc: string | null;
  total: number;
  taxed10: number;
  iva10: number;
  taxed5: number;
  iva5: number;
  exempt: number;
  irp_deductible: boolean;
  status: string;
  has_file: boolean;
}

export interface FiscalReport {
  month: string;
  rows: FiscalRow[];
  total: number;
  taxed10: number;
  iva10: number;
  taxed5: number;
  iva5: number;
  exempt: number;
  irp_total: number;
  missing_iva: number;
}

type AlertLevel = 'info' | 'warn' | 'danger';

export interface Alert {
  key: string;
  level: AlertLevel;
  title: string;
  body: string;
  link: string;
  date: string | null;
}

export interface NotificationSettings {
  notifications_enabled: boolean;
  notify_hour: number;
  notify_days_before: number;
  push_available: boolean;
  push_devices: number;
  telegram_available: boolean;
  telegram_linked: boolean;
  email_available: boolean;
  email_enabled: boolean;
  /** Dirección ya confirmada a la que llegan los avisos. */
  email_address: string | null;
  /** Dirección esperando el código de verificación. */
  email_pending: string | null;
}

export interface CategoryRule {
  id: number;
  match: 'ruc' | 'contains';
  pattern: string;
  learned: boolean;
  category: CategoryRef;
}

export interface Suggestion {
  category_id: number | null;
  source: 'ruc' | 'regla' | 'historial' | 'sugerencia' | null;
}

export interface TrashItem {
  id: number;
  entity: 'transaction' | 'invoice' | 'scheduled' | 'category';
  label: string;
  deleted_at: string;
}

export interface Backup {
  name: string;
  size: number;
  created_at: string;
}

export interface ImportMapping {
  date: number;
  description: number | null;
  amount: number | null;
  debit: number | null;
  credit: number | null;
  header_row: number;
  day_first: boolean;
}

export interface ImportRow {
  line: number;
  date: string | null;
  description: string;
  amount: number | null;
  kind: TransactionKind;
  category_id: number | null;
  duplicate: boolean;
  error: string | null;
}

export interface ImportPreview {
  columns: string[];
  mapping: ImportMapping | null;
  rows: ImportRow[];
  skipped: number;
}

export interface ImportItem {
  date: string;
  description: string;
  amount: number;
  kind: TransactionKind;
  category_id: number | null;
}
