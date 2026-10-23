import type { AccountType, Currency, PaymentMethod } from '../api/types';

export const ACCOUNT_TYPES: Record<AccountType, string> = {
  cash: 'Efectivo',
  bank: 'Banco',
  card: 'Tarjeta',
  wallet: 'Billetera',
};

const SYMBOLS: Record<Currency, string> = { PYG: '₲', USD: 'US$', ARS: '$', BRL: 'R$', EUR: '€' };
export const CURRENCIES = Object.keys(SYMBOLS) as Currency[];
export const currencySymbol = (c: Currency) => SYMBOLS[c];

export const PAYMENT_METHODS: Record<PaymentMethod, string> = {
  cash: 'Efectivo',
  debit: 'Débito',
  credit: 'Crédito',
  transfer: 'Transferencia',
  qr: 'QR',
};

const LOCALE = 'es-PY';

export function formatMoney(value: number, currency: Currency, opts: { short?: boolean; sign?: boolean } = {}): string {
  const abs = Math.abs(value);
  const decimals = currency === 'PYG' ? 0 : 2;
  let txt: string;
  if (opts.short && abs >= 1e6) txt = `${(abs / 1e6).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} M`;
  else if (opts.short && abs >= 1e4) txt = `${Math.round(abs / 1e3).toLocaleString(LOCALE)} mil`;
  else txt = abs.toLocaleString(LOCALE, { maximumFractionDigits: decimals });
  const prefix = value < 0 ? '− ' : opts.sign ? '+ ' : '';
  return `${prefix}${SYMBOLS[currency]} ${txt}`;
}

/** Convierte lo que escribe el usuario (385.000 · 1.234,56 · 1234.5) a número. */
export function parseMoney(input: string): number {
  const s = input.replace(/[^\d.,]/g, '');
  if (!s) return 0;
  let normalized = s;
  if (s.includes(',') && s.includes('.')) {
    normalized = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  } else if (s.includes(',')) {
    const tail = s.split(',').pop() ?? '';
    normalized = tail.length === 3 ? s.replace(/,/g, '') : s.replace(',', '.');
  } else if (s.includes('.')) {
    const parts = s.split('.');
    if ((parts.pop() ?? '').length === 3 || parts.length > 1) normalized = s.replace(/\./g, '');
  }
  const n = Number.parseFloat(normalized);
  return Number.isFinite(n) ? n : 0;
}

// El backend guarda hasta 12 dígitos enteros (Numeric(14, 2)).
const MAX_INTEGER_DIGITS = 12;

/** Agrupa miles mientras se escribe (solo monedas sin decimales). */
export function groupDigits(input: string, currency: Currency): string {
  if (currency !== 'PYG') return input;
  const digits = input.replace(/\D/g, '').replace(/^0+(?=\d)/, '').slice(0, MAX_INTEGER_DIGITS);
  return digits ? Number(digits).toLocaleString(LOCALE) : '';
}

/** Texto inicial de un campo de monto. Un monto con decimales no se convierte en otro número al editarlo. */
export function moneyInputText(value: number, currency: Currency): string {
  if (!value) return '';
  return currency === 'PYG' ? Math.round(value).toLocaleString(LOCALE) : String(value);
}

// ---------- Fechas (siempre en hora local, formato AAAA-MM-DD) ----------
const pad = (n: number) => String(n).padStart(2, '0');
export const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parseIso = (s: string) => {
  const [y = 0, m = 1, d = 1] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};
/** True si `s` es una fecha real en formato AAAA-MM-DD (rechaza 2026-02-31 o texto). */
export const isIsoDate = (s: string | null): s is string =>
  !!s && /^\d{4}-\d{2}-\d{2}$/.test(s) && isoDate(parseIso(s)) === s;
export const todayIso = () => isoDate(new Date());
export const monthOf = (iso: string) => iso.slice(0, 7);

export function shiftMonth(month: string, delta: number): string {
  const d = parseIso(`${month}-01`);
  d.setMonth(d.getMonth() + delta);
  return monthOf(isoDate(d));
}

export function monthBounds(month: string): { start: string; end: string } {
  const d = parseIso(`${month}-01`);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return { start: `${month}-01`, end: isoDate(last) };
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const monthLabel = (month: string) =>
  capitalize(parseIso(`${month}-01`).toLocaleDateString(LOCALE, { month: 'long', year: 'numeric' }));

export function formatDate(iso: string | null, style: 'short' | 'long' | 'weekday' = 'short'): string {
  if (!iso) return '—';
  const opts: Intl.DateTimeFormatOptions =
    style === 'long'
      ? { weekday: 'long', day: 'numeric', month: 'long' }
      : style === 'weekday'
        ? { weekday: 'short' }
        : { day: 'numeric', month: 'short' };
  return capitalize(parseIso(iso).toLocaleDateString(LOCALE, opts).replace('.', ''));
}

export function relativeDay(iso: string): string {
  const diff = Math.round((parseIso(iso).getTime() - parseIso(todayIso()).getTime()) / 86_400_000);
  if (diff === 0) return 'Hoy';
  if (diff === 1) return 'Mañana';
  if (diff === -1) return 'Ayer';
  return diff > 0 ? `En ${diff} días` : `Hace ${-diff} días`;
}

export function tint(hex: string, alpha = 0.16): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
