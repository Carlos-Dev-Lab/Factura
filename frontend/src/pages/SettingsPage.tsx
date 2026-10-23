import { useSearchParams } from 'react-router-dom';

import { Icon, type IconName } from '../components/Icon';
import { CategoriesSection } from '../features/settings/CategoriesSection';
import { DataSection } from '../features/settings/DataSection';
import { NotificationsSection } from '../features/settings/NotificationsSection';
import { ProfileSection } from '../features/settings/ProfileSection';
import { RulesSection } from '../features/settings/RulesSection';
import { ScheduledSection } from '../features/settings/ScheduledSection';
import { SecuritySection } from '../features/settings/SecuritySection';
import { TrashSection } from '../features/settings/TrashSection';

const SECTIONS = [
  { id: 'perfil', label: 'Perfil y presupuesto', short: 'Perfil', icon: 'user', Component: ProfileSection },
  { id: 'pagos', label: 'Pagos fijos', short: 'Pagos fijos', icon: 'calendar', Component: ScheduledSection },
  { id: 'categorias', label: 'Categorías', short: 'Categorías', icon: 'tag', Component: CategoriesSection },
  { id: 'reglas', label: 'Reglas automáticas', short: 'Reglas', icon: 'rules', Component: RulesSection },
  { id: 'avisos', label: 'Avisos', short: 'Avisos', icon: 'bell', Component: NotificationsSection },
  { id: 'papelera', label: 'Papelera', short: 'Papelera', icon: 'trash', Component: TrashSection },
  { id: 'seguridad', label: 'Seguridad', short: 'Seguridad', icon: 'lock', Component: SecuritySection },
  { id: 'datos', label: 'Datos y respaldos', short: 'Datos', icon: 'download', Component: DataSection },
] as const satisfies readonly { id: string; label: string; short: string; icon: IconName; Component: () => JSX.Element }[];

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const current = SECTIONS.find((s) => s.id === params.get('seccion')) ?? SECTIONS[0];
  const { Component } = current;

  return (
    <div className="settings">
      <nav className="settings-nav" aria-label="Secciones de ajustes">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            className={s.id === current.id ? 'on' : ''}
            aria-current={s.id === current.id ? 'page' : undefined}
            onClick={() => setParams({ seccion: s.id }, { replace: true })}
          >
            <Icon name={s.icon} size={18} />
            <span className="long">{s.label}</span>
            <span className="short">{s.short}</span>
          </button>
        ))}
      </nav>
      <div className="settings-body">
        <Component key={current.id} />
      </div>
    </div>
  );
}
