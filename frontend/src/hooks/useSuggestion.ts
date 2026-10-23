import { useEffect, useState } from 'react';

import { categoriesApi } from '../api/endpoints';
import type { Suggestion, TransactionKind } from '../api/types';

const DEBOUNCE_MS = 400;
const MIN_TEXT = 3;

/** Categoría sugerida para lo que se está escribiendo (según reglas e historial del usuario). */
export function useCategorySuggestion(kind: TransactionKind, text: string, enabled = true): Suggestion | null {
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  useEffect(() => {
    const clean = text.trim();
    if (!enabled || clean.length < MIN_TEXT) {
      setSuggestion(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      categoriesApi
        .suggest(kind, clean)
        .then((s) => !cancelled && setSuggestion(s.category_id ? s : null))
        .catch(() => undefined);
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [kind, text, enabled]);
  return suggestion;
}

export const SUGGESTION_SOURCE: Record<NonNullable<Suggestion['source']>, string> = {
  ruc: 'Sugerida por el RUC del proveedor',
  regla: 'Sugerida por una de tus reglas',
  historial: 'Sugerida por lo que elegiste antes',
  sugerencia: 'Sugerida automáticamente',
};
