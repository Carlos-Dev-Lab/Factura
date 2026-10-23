import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { authApi } from '../../api/endpoints';
import { Field } from '../../components/fields';
import { GoogleLogo } from '../../components/GoogleLogo';
import { Icon } from '../../components/Icon';
import { useToast } from '../../context/ToastContext';
import { keys, useUser } from '../../hooks/queries';
import { MIN_PASSWORD, passwordChecks, passwordStrength, passwordValid } from '../../lib/password';
import { useLogout } from '../auth/useLogout';
import { SectionHeader } from './SectionHeader';

/** Resultado con el que vuelve "Vincular cuenta de Google" (?google=...). */
const GOOGLE_RESULT: Record<string, string> = {
  vinculado: 'Listo: ya podés entrar con tu cuenta de Google.',
  'ya-vinculada': 'Esa cuenta de Google ya está vinculada a otro usuario.',
  expirado: 'El vínculo con Google se demoró o se cerró la sesión. Volvé a probar.',
  cancelado: 'Cancelaste el vínculo con Google.',
  demasiados: 'Demasiados intentos. Esperá unos minutos y volvé a probar.',
};
const GOOGLE_FAILED = 'Google no pudo confirmar tu identidad. Volvé a probar.';

function PasswordCard() {
  const { email, has_password: hasPassword } = useUser();
  const qc = useQueryClient();
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  const s = passwordStrength(next, email);
  const failing = passwordChecks(next, email).filter((c) => !c.ok);
  const mismatch = confirm.length > 0 && confirm !== next;
  const canSubmit = (current || !hasPassword) && passwordValid(next, email) && next === confirm && !busy;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    try {
      qc.setQueryData(keys.me, await authApi.changePassword(hasPassword ? current : null, next));
      setCurrent('');
      setNext('');
      setConfirm('');
      toast(
        hasPassword
          ? 'Contraseña actualizada. Se cerraron las demás sesiones.'
          : 'Contraseña creada. Ahora también podés entrar con tu email.',
      );
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const type = show ? 'text' : 'password';
  return (
    <form className="card" onSubmit={submit}>
      <SectionHeader
        title={hasPassword ? 'Cambiar contraseña' : 'Crear contraseña'}
        description={
          hasPassword
            ? 'Al cambiarla se cierran las sesiones abiertas en otros dispositivos.'
            : 'Tu cuenta se creó con Google. Con una contraseña también podés entrar con tu email.'
        }
      />
      <div className="form narrow">
        <input type="email" autoComplete="username" value={email} readOnly hidden />
        {hasPassword && (
          <Field label="Contraseña actual">
            <input
              type={type}
              required
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </Field>
        )}
        <Field label="Nueva contraseña">
          <input
            type={type}
            required
            minLength={MIN_PASSWORD}
            maxLength={128}
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        {next && (
          <div className={`strength l${s.level}`} aria-live="polite">
            <div className="bars4">
              {[1, 2, 3].map((i) => (
                <i key={i} className={s.level >= i ? 'on' : ''} />
              ))}
            </div>
            <span>{s.level ? s.label : `Falta: ${failing.map((c) => c.label.toLowerCase()).join(' · ')}`}</span>
          </div>
        )}
        <Field label="Repetir nueva contraseña" hint={mismatch ? 'Las contraseñas no coinciden' : undefined}>
          <input
            type={type}
            required
            autoComplete="new-password"
            aria-invalid={mismatch}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        <label className="check">
          <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
          Mostrar contraseñas
        </label>
        <div className="row-actions start">
          <button className="btn mint" disabled={!canSubmit}>
            {hasPassword ? 'Cambiar contraseña' : 'Crear contraseña'}
          </button>
        </div>
      </div>
    </form>
  );
}

function GoogleCard() {
  const user = useUser();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: config } = useQuery({ queryKey: ['auth-config'], queryFn: authApi.config });
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const announced = useRef(false);

  // Vuelta de Google: se avisa el resultado una vez y se limpia la dirección.
  useEffect(() => {
    const reason = params.get('google');
    if (!reason || announced.current) return;
    announced.current = true;
    toast(GOOGLE_RESULT[reason] ?? GOOGLE_FAILED);
    void qc.invalidateQueries({ queryKey: keys.me });
    const rest = new URLSearchParams(params);
    rest.delete('google');
    setParams(rest, { replace: true });
  }, [params, setParams, toast, qc]);

  const link = async () => {
    setBusy(true);
    try {
      const { url } = await authApi.googleLink();
      window.location.assign(url); // a Google y de vuelta a esta pantalla
    } catch (err) {
      toast((err as Error).message);
      setBusy(false);
    }
  };

  const unlink = async () => {
    setBusy(true);
    try {
      await authApi.googleUnlink();
      qc.setQueryData(keys.me, { ...user, google_email: null });
      toast('Cuenta de Google desvinculada');
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Sin Google configurado (o entrando por una dirección que Google no acepta) y sin vínculo: nada que mostrar.
  if (!user.google_email && !config?.google_login) return null;

  return (
    <section className="card">
      <SectionHeader
        title="Cuenta de Google"
        description="Entrá con un toque usando tu cuenta de Google, sin escribir la contraseña."
      />
      {user.google_email ? (
        <div className="stack tight">
          <div className="row-actions start">
            <span className="status paid">Vinculada</span>
            <span className="soft">{user.google_email}</span>
          </div>
          <div className="row-actions start">
            <button className="btn small" disabled={busy || !user.has_password} onClick={() => void unlink()}>
              Desvincular
            </button>
          </div>
          {!user.has_password && (
            <p className="hint">
              Para desvincularla, primero creá una contraseña: si no, no tendrías otra forma de entrar.
            </p>
          )}
        </div>
      ) : (
        <div className="row-actions start">
          <button className="btn au-google" disabled={busy} onClick={() => void link()}>
            <GoogleLogo />
            Vincular cuenta de Google
          </button>
        </div>
      )}
    </section>
  );
}

export function SecuritySection() {
  const { email } = useUser();
  const logout = useLogout();

  return (
    <div className="stack">
      <PasswordCard />
      <GoogleCard />

      <section className="card">
        <SectionHeader title="Sesión" description={`Iniciaste sesión como ${email}.`} />
        <div className="stack">
          <div className="row-actions start">
            <button className="btn" onClick={() => logout()}>
              <Icon name="logout" size={18} />
              Cerrar sesión en este dispositivo
            </button>
            <button className="btn" onClick={() => logout(true)}>
              <Icon name="lock" size={18} />
              Cerrar sesión en todos los dispositivos
            </button>
          </div>
          <p className="hint">
            Usá la segunda opción si perdiste el celular o entraste desde una computadora ajena: vas a tener que
            volver a ingresar en todos lados y ningún dispositivo seguirá recibiendo tus avisos.
          </p>
        </div>
      </section>
    </div>
  );
}
