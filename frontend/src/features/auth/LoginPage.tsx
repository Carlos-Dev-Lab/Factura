import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { ApiError } from '../../api/client';
import { GOOGLE_LOGIN_URL, authApi } from '../../api/endpoints';
import { GoogleLogo } from '../../components/GoogleLogo';
import { Icon, type IconName } from '../../components/Icon';
import { keys } from '../../hooks/queries';
import { MAX_PASSWORD, emailValid, passwordChecks, passwordStrength, passwordValid } from '../../lib/password';
import { claimThisDevice } from '../../lib/pwa';

type FieldId = 'name' | 'email' | 'password' | 'confirm';

const GOOGLE_FAILED = 'Google no pudo confirmar tu identidad. Volvé a probar.';

/** Motivos con los que vuelve el ingreso con Google (?google=...). */
const GOOGLE_ERRORS: Record<string, string> = {
  cancelado: 'Cancelaste el ingreso con Google.',
  expirado: 'El ingreso con Google se demoró o se abrió en otra pestaña. Volvé a probar.',
  'sin-cuenta':
    'No hay ninguna cuenta con esa cuenta de Google y el registro de cuentas nuevas está cerrado. Pedile acceso a quien administra el sistema.',
  vincular:
    'Ya existe una cuenta con ese email. Entrá con tu contraseña y vinculá Google desde Ajustes → Seguridad.',
  'no-disponible':
    'El ingreso con Google funciona entrando por localhost o por la dirección HTTPS del servidor, no por la IP de la red.',
  demasiados: 'Demasiados intentos. Esperá unos minutos y volvé a probar.',
};

let googleReason: string | null | undefined;

/** Lee el motivo una sola vez y lo saca de la dirección (para que no reaparezca al recargar). */
function takeGoogleError(): string {
  if (googleReason === undefined) {
    const url = new URL(window.location.href);
    googleReason = url.searchParams.get('google');
    if (googleReason !== null) {
      url.searchParams.delete('google');
      window.history.replaceState(null, '', url.pathname + url.search);
    }
  }
  return googleReason === null ? '' : (GOOGLE_ERRORS[googleReason] ?? GOOGLE_FAILED);
}

interface AuthFieldProps {
  id: FieldId;
  label: string;
  icon: IconName;
  error: string;
  trailing?: ReactNode;
  children: (props: { id: string; 'aria-invalid': boolean; 'aria-describedby'?: string }) => ReactNode;
}

/** Campo con ícono, error debajo y descripción accesible (aria-describedby). */
function AuthField({ id, label, icon, error, trailing, children }: AuthFieldProps) {
  return (
    <label className={`f au-field ${error ? 'invalid' : ''}`}>
      {label}
      <span className="au-input">
        <Icon name={icon} size={18} />
        {children({ id: `au-${id}`, 'aria-invalid': !!error, 'aria-describedby': error ? `${id}-error` : undefined })}
        {trailing}
      </span>
      {error && (
        <span className="au-err" id={`${id}-error`} role="alert">
          {error}
        </span>
      )}
    </label>
  );
}

export function LoginPage({ onAbout }: { onAbout?: () => void }) {
  const qc = useQueryClient();
  const { data: config } = useQuery({ queryKey: ['auth-config'], queryFn: authApi.config });
  const firstUser = config?.first_user ?? false;
  const canRegister = config?.registration_open ?? false;
  // Con el registro abierto se muestra el ingreso y un enlace para crear cuenta.
  // "Crear cuenta" desde la portada llega con ?crear=1.
  const [wantsRegister, setWantsRegister] = useState(() => new URLSearchParams(window.location.search).has('crear'));
  const registering = firstUser || (canRegister && wantsRegister);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<FieldId, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  // Motivo con el que volvió el ingreso con Google: se muestra junto al botón, arriba.
  const [googleError, setGoogleError] = useState(takeGoogleError);
  // Ya mostrado: si más tarde se vuelve a esta pantalla (al cerrar sesión), no reaparece.
  useEffect(
    () => () => {
      googleReason = null;
    },
    [],
  );
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  const problems: Record<FieldId, string> = {
    name: registering && name.trim().length < 2 ? 'Escribí tu nombre (al menos 2 letras).' : '',
    email: !email.trim()
      ? 'Ingresá tu email.'
      : !emailValid(email)
        ? 'Ese email no parece válido. Ejemplo: nombre@gmail.com'
        : '',
    password: !password
      ? 'Ingresá tu contraseña.'
      : registering && !passwordValid(password, email)
        ? 'La contraseña todavía no cumple los requisitos de abajo.'
        : '',
    confirm: registering && confirm !== password ? 'Las contraseñas no coinciden.' : '',
  };
  // Los errores aparecen al salir del campo o al intentar enviar, no mientras se empieza a escribir.
  const shown = (id: FieldId) => ((touched[id] || submitted) && problems[id]) || '';
  const blur = (id: FieldId) => () => setTouched((t) => ({ ...t, [id]: true }));
  const checks = passwordChecks(password, email);
  const strength = passwordStrength(password, email);

  const switchMode = () => {
    setWantsRegister(!wantsRegister);
    setError('');
    setSubmitted(false);
    setTouched({});
    setConfirm('');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setGoogleError('');
    setError('');
    const firstBad = (['name', 'email', 'password', 'confirm'] as FieldId[]).find((id) => problems[id]);
    if (firstBad) {
      form.current?.querySelector<HTMLInputElement>(`#au-${firstBad}`)?.focus();
      return;
    }
    setBusy(true);
    try {
      const user = registering
        ? await authApi.register(email.trim(), password, name.trim())
        : await authApi.login(email.trim(), password);
      // Si la sesión anterior venció sin recargar la página, la caché todavía tiene sus datos
      // (que pueden ser de otra cuenta): se descartan antes de mostrar la app.
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== keys.me[0] });
      qc.setQueryData(keys.me, user);
      void claimThisDevice();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 401
          ? 'El email o la contraseña no son correctos.'
          : status === 0
            ? 'No se pudo conectar con el servidor. Revisá tu conexión y volvé a probar.'
            : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  };

  const type = show ? 'text' : 'password';
  const eye = (
    <button
      type="button"
      className="au-eye"
      onClick={() => setShow(!show)}
      aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}
      aria-pressed={show}
    >
      <Icon name={show ? 'eyeOff' : 'eye'} size={18} />
    </button>
  );

  return (
    <div className="au">
      <header className="au-top">
        <button type="button" className="brand au-brand" onClick={onAbout} disabled={!onAbout}>
          <span className="logo" aria-hidden="true">
            <Icon name="invoice" size={20} stroke={2.2} />
          </span>
          Factura
        </button>
        {onAbout && (
          <button type="button" className="btn small au-about" onClick={onAbout}>
            <Icon name="left" size={16} />
            <span className="au-about-long">Qué es Factura</span>
            <span className="au-about-short">Inicio</span>
          </button>
        )}
      </header>

      <main className="au-main">
        <section className="au-side">
          <span className="pill mint">{registering ? 'Cuenta nueva' : 'Hola de nuevo'}</span>
          <h2>
            {registering ? (
              <>
                Ordená tus cuentas <span className="lp-accent">desde hoy</span>.
              </>
            ) : (
              <>
                Tus números, <span className="lp-accent">como los dejaste</span>.
              </>
            )}
          </h2>
          <p className="lp-lead">
            {registering
              ? 'En un minuto tenés tu panel listo: cargá una factura, anotá un gasto y la app te avisa antes de cada vencimiento.'
              : 'Entrá para ver el saldo del mes, lo que vence pronto y cómo vas con tus presupuestos.'}
          </p>
          <ul className="lp-checks col">
            {[
              'Cada cuenta ve solo sus propios datos',
              'Contraseña cifrada: nadie más la puede ver',
              'Tus datos quedan en este servidor',
            ].map((t) => (
              <li key={t}>
                <Icon name="check" size={16} stroke={2.6} />
                {t}
              </li>
            ))}
          </ul>
          <div className="au-note" aria-hidden="true">
            <span className="lp-chip amber">
              <Icon name="bell" size={16} />
            </span>
            <span>
              <b>La factura de ANDE vence mañana</b>
              <small>₲ 231.500 · aviso de ejemplo</small>
            </span>
          </div>
        </section>

        <form ref={form} className="au-card" onSubmit={submit} noValidate>
          <div className="au-head">
            <h1>{registering ? 'Creá tu cuenta' : 'Iniciá sesión'}</h1>
            <p className="muted">
              {firstUser
                ? 'Es la primera vez que se usa este sistema: creá la cuenta de administrador.'
                : registering
                  ? 'Completá tus datos para crear tu cuenta.'
                  : 'Ingresá con tu email y tu contraseña.'}
            </p>
          </div>

          {googleError && (
            <div className="au-alert" role="alert">
              <Icon name="alert" size={18} />
              {googleError}
            </div>
          )}

          {config?.google_login && (
            <>
              <a className="btn block au-google" href={GOOGLE_LOGIN_URL}>
                <GoogleLogo />
                Continuar con Google
              </a>
              <div className="au-or">
                <span>o con tu email</span>
              </div>
            </>
          )}

          {registering && (
            <AuthField id="name" label="Nombre" icon="user" error={shown('name')}>
              {(p) => (
                <input
                  {...p}
                  autoComplete="name"
                  maxLength={80}
                  placeholder="¿Cómo te llamamos?"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={blur('name')}
                />
              )}
            </AuthField>
          )}

          <AuthField id="email" label="Email" icon="mail" error={shown('email')}>
            {(p) => (
              <input
                {...p}
                type="email"
                inputMode="email"
                autoComplete={registering ? 'email' : 'username'}
                autoCapitalize="none"
                spellCheck={false}
                maxLength={254}
                placeholder="nombre@gmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={blur('email')}
              />
            )}
          </AuthField>

          <AuthField id="password" label="Contraseña" icon="lock" error={shown('password')} trailing={eye}>
            {(p) => (
              <input
                {...p}
                type={type}
                autoComplete={registering ? 'new-password' : 'current-password'}
                maxLength={MAX_PASSWORD}
                placeholder={registering ? 'Mínimo 10 caracteres' : 'Tu contraseña'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onBlur={blur('password')}
              />
            )}
          </AuthField>

          {registering && (
            <div className="au-rules" aria-live="polite">
              <div className={`strength l${strength.level}`}>
                <div className="bars4">
                  {[1, 2, 3].map((i) => (
                    <i key={i} className={strength.level >= i ? 'on' : ''} />
                  ))}
                </div>
                <span>{password ? strength.label : 'Elegí una contraseña'}</span>
              </div>
              <ul>
                {checks.map((c) => (
                  <li key={c.id} className={c.ok ? 'ok' : ''}>
                    <Icon name={c.ok ? 'check' : 'close'} size={14} stroke={2.6} />
                    {c.label}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {registering && (
            <AuthField id="confirm" label="Repetir contraseña" icon="lock" error={shown('confirm')}>
              {(p) => (
                <input
                  {...p}
                  type={type}
                  autoComplete="new-password"
                  maxLength={MAX_PASSWORD}
                  placeholder="Escribila de nuevo"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  onBlur={blur('confirm')}
                />
              )}
            </AuthField>
          )}

          {error && (
            <div className="au-alert" role="alert">
              <Icon name="alert" size={18} />
              {error}
            </div>
          )}

          <button className="btn mint block lp-big" disabled={busy}>
            {busy ? 'Un momento…' : registering ? 'Crear cuenta' : 'Entrar'}
            {!busy && <Icon name="right" size={18} />}
          </button>

          {canRegister && !firstUser && (
            <p className="au-switch">
              {wantsRegister ? '¿Ya tenés cuenta?' : '¿No tenés cuenta?'}{' '}
              <button type="button" onClick={switchMode}>
                {wantsRegister ? 'Iniciá sesión' : 'Creá una'}
              </button>
            </p>
          )}
          {firstUser && <p className="au-fine">Esta va a ser la cuenta principal del sistema.</p>}
        </form>
      </main>
    </div>
  );
}
