import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { ApiError } from './api/client';
import { Layout } from './components/Layout';
import { Loading } from './components/Loading';
import { DialogsProvider } from './context/DialogsContext';
import { MonthProvider } from './context/MonthContext';
import { LoginPage } from './features/auth/LoginPage';
import { LandingPage } from './features/landing/LandingPage';
import { useMe } from './hooks/queries';
import { claimThisDevice } from './lib/pwa';
import { AccountsPage } from './pages/AccountsPage';
import { CalendarPage } from './pages/CalendarPage';
import { DailyPage } from './pages/DailyPage';
import { DashboardPage } from './pages/DashboardPage';
import { InvoicesPage } from './pages/InvoicesPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';

// Si la sesión venció mientras se usaba la app, se vuelve directo al ingreso (no a la portada).
let hadSession = false;

const isInstalledApp = () =>
  window.matchMedia?.('(display-mode: standalone)').matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true;

/** Sin sesión: la portada en "/" (para quien llega por primera vez) y el ingreso en "/ingresar". */
function LoggedOut() {
  const [landing, setLanding] = useState(
    () => window.location.pathname === '/' && !hadSession && !isInstalledApp(),
  );

  useEffect(() => {
    const onBack = () => setLanding(window.location.pathname === '/');
    window.addEventListener('popstate', onBack);
    return () => window.removeEventListener('popstate', onBack);
  }, []);

  const go = (path: string, showLanding: boolean) => {
    window.history.pushState({}, '', path);
    setLanding(showLanding);
    window.scrollTo(0, 0);
  };

  return landing ? (
    <LandingPage onEnter={(register) => go(register ? '/ingresar?crear=1' : '/ingresar', false)} />
  ) : (
    <LoginPage onAbout={() => go('/', true)} />
  );
}

export function App() {
  const me = useMe();

  // Recién volvió de entrar con Google: este dispositivo pasa a recibir los avisos de esta cuenta
  // (lo mismo que hace el ingreso con contraseña).
  useEffect(() => {
    if (!me.data) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get('ingreso') !== 'google') return;
    url.searchParams.delete('ingreso');
    window.history.replaceState(null, '', url.pathname + url.search);
    void claimThisDevice();
  }, [me.data]);

  if (me.isPending) return <Loading />;
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) return <Loading error={me.error} />;
  if (!me.data) return <LoggedOut />;
  hadSession = true;

  return (
    <BrowserRouter>
      <MonthProvider>
        <DialogsProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="facturas" element={<InvoicesPage />} />
              <Route path="calendario" element={<CalendarPage />} />
              <Route path="gastos" element={<DailyPage />} />
              <Route path="cuentas" element={<AccountsPage />} />
              <Route path="reportes" element={<ReportsPage />} />
              <Route path="ajustes" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </DialogsProvider>
      </MonthProvider>
    </BrowserRouter>
  );
}
