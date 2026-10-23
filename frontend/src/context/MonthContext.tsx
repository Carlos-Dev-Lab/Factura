import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

import { monthOf, todayIso } from '../lib/format';

interface MonthState {
  month: string;
  setMonth: (month: string) => void;
  /** Día por defecto para registrar movimientos: hoy si es el mes actual, si no el día 1. */
  defaultDay: string;
}

const MonthContext = createContext<MonthState | null>(null);

export function MonthProvider({ children }: { children: ReactNode }) {
  const [month, setMonth] = useState(() => monthOf(todayIso()));
  const value = useMemo(() => {
    const today = todayIso();
    return { month, setMonth, defaultDay: monthOf(today) === month ? today : `${month}-01` };
  }, [month]);
  return <MonthContext.Provider value={value}>{children}</MonthContext.Provider>;
}

export function useMonth(): MonthState {
  const ctx = useContext(MonthContext);
  if (!ctx) throw new Error('useMonth debe usarse dentro de MonthProvider');
  return ctx;
}
