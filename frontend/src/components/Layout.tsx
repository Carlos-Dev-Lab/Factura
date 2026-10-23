import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { useDialogs } from '../context/DialogsContext';
import { useMonth } from '../context/MonthContext';
import { AlertsBell } from '../features/alerts/AlertsPanel';
import { useLogout } from '../features/auth/useLogout';
import { monthLabel, monthOf, shiftMonth, todayIso } from '../lib/format';
import { Icon, type IconName } from './Icon';

interface NavItem {
  to: string;
  label: string;
  short: string;
  icon: IconName;
  month?: boolean; // muestra el selector de mes
}

const NAV: NavItem[] = [
  { to: '/', label: 'Panel', short: 'Panel', icon: 'dashboard', month: true },
  { to: '/facturas', label: 'Facturas', short: 'Facturas', icon: 'invoice' },
  { to: '/calendario', label: 'Calendario', short: 'Pagos', icon: 'calendar', month: true },
  { to: '/gastos', label: 'Gastos diarios', short: 'Gastos', icon: 'chart', month: true },
  { to: '/cuentas', label: 'Cuentas', short: 'Cuentas', icon: 'wallet' },
  { to: '/reportes', label: 'Reportes', short: 'Reportes', icon: 'report' },
  { to: '/ajustes', label: 'Ajustes', short: 'Ajustes', icon: 'settings' },
];
const byPath = (to: string) => NAV.find((n) => n.to === to)!;
// En el celular: 2 accesos, botón central "+", 1 acceso y "Más".
const MOBILE_MAIN = [byPath('/'), byPath('/calendario')];
const MOBILE_MORE = [byPath('/facturas'), byPath('/cuentas'), byPath('/reportes'), byPath('/ajustes')];

function MonthSwitcher() {
  const { month, setMonth } = useMonth();
  return (
    <div className="month-switch" role="group" aria-label="Mes">
      <button className="icon-btn" onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Mes anterior">
        <Icon name="left" size={18} stroke={2.4} />
      </button>
      <button className="month-label" onClick={() => setMonth(monthOf(todayIso()))} title="Volver al mes actual">
        {monthLabel(month)}
      </button>
      <button className="icon-btn" onClick={() => setMonth(shiftMonth(month, 1))} aria-label="Mes siguiente">
        <Icon name="right" size={18} stroke={2.4} />
      </button>
    </div>
  );
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-label={title}>
        <div className="sheet-handle" aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}

export function Layout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { openTransaction, openTransfer, pickInvoiceFile } = useDialogs();
  const logout = useLogout();
  const [sheet, setSheet] = useState<'add' | 'more' | null>(null);
  const current = NAV.find((n) => n.to === pathname) ?? NAV[0]!;
  const today = new Date().toLocaleDateString('es-PY', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  // Accesos directos del ícono instalado ("Nuevo gasto", "Escanear factura").
  useEffect(() => {
    if (params.get('nuevo') === 'gasto') {
      openTransaction({ kind: 'expense' });
      params.delete('nuevo');
      setParams(params, { replace: true });
    } else if (params.get('escanear')) {
      // El navegador no deja abrir la cámara sin un toque del usuario: se muestra la pantalla de facturas.
      navigate('/facturas', { replace: true });
    }
  }, [params, setParams, openTransaction, navigate]);

  // Al navegar se cierran los menús del celular.
  useEffect(() => setSheet(null), [pathname]);

  const quick = (action: () => void) => {
    setSheet(null);
    action();
  };

  return (
    <div className="shell">
      <nav className="side" aria-label="Principal">
        <NavLink className="brand" to="/">
          <span className="logo" aria-hidden="true">
            <Icon name="invoice" size={22} stroke={2.2} />
          </span>
          Factura
        </NavLink>
        <div className="nav-links">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end className={({ isActive }) => (isActive ? 'on' : '')}>
              <Icon name={n.icon} />
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="side-cta card raised">
          <strong>Analizá una factura</strong>
          <p>Subí un PDF, una foto o el XML de la factura electrónica y se completan los datos solos.</p>
          <button className="btn mint" onClick={() => pickInvoiceFile()}>
            Subir factura
          </button>
        </div>
        <button className="btn ghost" onClick={() => logout()}>
          <Icon name="logout" size={18} />
          Cerrar sesión
        </button>
      </nav>

      <main className="main">
        <header className="top">
          <div>
            <div className="muted">{today}</div>
            <h1>{current.label}</h1>
          </div>
          <div className="top-actions">
            {current.month && <MonthSwitcher />}
            <AlertsBell />
            <button className="btn violet hide-sm" onClick={() => openTransaction()}>
              + Nuevo movimiento
            </button>
          </div>
        </header>
        <Outlet />
      </main>

      <nav className="bottom" aria-label="Navegación móvil">
        {MOBILE_MAIN.map((n) => (
          <NavLink key={n.to} to={n.to} end className={({ isActive }) => (isActive ? 'on' : '')} aria-label={n.label}>
            <Icon name={n.icon} />
            <span>{n.short}</span>
          </NavLink>
        ))}
        <button className="fab" onClick={() => setSheet('add')} aria-label="Agregar" aria-expanded={sheet === 'add'}>
          <Icon name="plus" size={26} stroke={2.6} />
        </button>
        <NavLink to="/gastos" end className={({ isActive }) => (isActive ? 'on' : '')} aria-label="Gastos diarios">
          <Icon name="chart" />
          <span>Gastos</span>
        </NavLink>
        <button
          className={MOBILE_MORE.some((n) => n.to === pathname) ? 'on' : ''}
          onClick={() => setSheet('more')}
          aria-label="Más secciones"
          aria-expanded={sheet === 'more'}
        >
          <Icon name="more" />
          <span>Más</span>
        </button>
      </nav>

      {sheet === 'add' && (
        <Sheet title="Agregar" onClose={() => setSheet(null)}>
          <div className="sheet-grid">
            <button className="sheet-action coral" onClick={() => quick(() => openTransaction({ kind: 'expense' }))}>
              <Icon name="expense" size={22} />
              Gasto
            </button>
            <button className="sheet-action mint" onClick={() => quick(() => openTransaction({ kind: 'income' }))}>
              <Icon name="income" size={22} />
              Ingreso
            </button>
            <button className="sheet-action" onClick={() => quick(() => pickInvoiceFile(true))}>
              <Icon name="camera" size={22} />
              Foto de factura
            </button>
            <button className="sheet-action" onClick={() => quick(() => pickInvoiceFile())}>
              <Icon name="upload" size={22} />
              Archivo (PDF/XML)
            </button>
            <button className="sheet-action violet" onClick={() => quick(() => openTransfer())}>
              <Icon name="transfer" size={22} />
              Transferencia
            </button>
          </div>
        </Sheet>
      )}
      {sheet === 'more' && (
        <Sheet title="Más secciones" onClose={() => setSheet(null)}>
          <div className="sheet-list">
            {MOBILE_MORE.map((n) => (
              <button key={n.to} className={pathname === n.to ? 'on' : ''} onClick={() => quick(() => navigate(n.to))}>
                <Icon name={n.icon} />
                {n.label}
              </button>
            ))}
            <button onClick={() => quick(logout)}>
              <Icon name="logout" />
              Cerrar sesión
            </button>
          </div>
        </Sheet>
      )}
    </div>
  );
}
