import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { notificationsApi } from '../../api/endpoints';
import type { NotificationSettings } from '../../api/types';
import { Field, Switch } from '../../components/fields';
import { Icon } from '../../components/Icon';
import { Loading } from '../../components/Loading';
import { useToast } from '../../context/ToastContext';
import { keys, useFinancialMutation, useNotificationSettings, useUser } from '../../hooks/queries';
import { emailValid } from '../../lib/password';
import { currentSubscription, disablePush, enablePush, pushSupported } from '../../lib/pwa';
import { SectionHeader } from './SectionHeader';

const HOURS = Array.from({ length: 16 }, (_, i) => i + 6); // 6:00 a 21:00

function PushCard({ devices }: { devices: number }) {
  const toast = useToast();
  const [enabledHere, setEnabledHere] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const supported = pushSupported();
  const qc = useQueryClient();

  useEffect(() => {
    void currentSubscription().then((s) => setEnabledHere(!!s));
  }, []);

  const toggle = async (on: boolean) => {
    setBusy(true);
    try {
      if (on) {
        const result = await enablePush();
        if (result === 'denied') toast('El navegador bloqueó las notificaciones. Habilitalas en los permisos del sitio.');
        setEnabledHere(result === 'enabled');
        if (result === 'enabled') toast('Listo: este dispositivo va a recibir los avisos');
      } else {
        await disablePush();
        setEnabledHere(false);
      }
      void qc.invalidateQueries({ queryKey: keys.notifications });
    } catch (err) {
      toast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <SectionHeader
        title="Notificaciones en este dispositivo"
        description="Avisos en el celular o la computadora aunque la app esté cerrada, como los de cualquier aplicación."
      />
      {supported ? (
        <div className="switch-row">
          <div>
            <b>Recibir notificaciones aquí</b>
            <span className="hint">
              {devices === 0
                ? 'Todavía no hay dispositivos suscritos.'
                : `${devices} dispositivo${devices === 1 ? '' : 's'} suscrito${devices === 1 ? '' : 's'} en total.`}
            </span>
          </div>
          <Switch checked={!!enabledHere} disabled={busy || enabledHere === null} label="Recibir notificaciones aquí" onChange={(v) => void toggle(v)} />
        </div>
      ) : (
        <div className="found mid">
          <Icon name="alert" size={18} />
          <span>
            Este navegador no permite notificaciones con la conexión actual. Necesitan HTTPS (por ejemplo con
            Tailscale). En iPhone, además, hay que agregar la app a la pantalla de inicio.
          </span>
        </div>
      )}
    </section>
  );
}

function TelegramCard({ linked, available }: { linked: boolean; available: boolean }) {
  const toast = useToast();
  const [link, setLink] = useState<string | null>(null);
  const create = useFinancialMutation(notificationsApi.linkTelegram, undefined, ['notifications']);
  const unlink = useFinancialMutation(notificationsApi.unlinkTelegram, 'Telegram desvinculado', ['notifications']);

  return (
    <section className="card">
      <SectionHeader
        title="Telegram"
        description="Recibí el resumen de vencimientos en un chat de Telegram. Sirve también si no tenés HTTPS."
      />
      {!available ? (
        <p className="hint">
          Para activarlo, creá un bot con @BotFather en Telegram y agregá su token en el archivo <code>.env</code> del
          servidor (<code>TELEGRAM_BOT_TOKEN</code>). Después volvé a esta pantalla.
        </p>
      ) : linked ? (
        <div className="row-actions start">
          <span className="status paid">Vinculado</span>
          <button className="btn small" onClick={() => unlink.mutate(undefined)}>
            Desvincular
          </button>
        </div>
      ) : link ? (
        <div className="stack tight">
          <p className="soft">
            Abrí el enlace, tocá <b>Iniciar</b> en Telegram y volvé aquí. El enlace vence en 15 minutos.
          </p>
          <a className="btn mint" href={link} target="_blank" rel="noopener noreferrer">
            Abrir Telegram
          </a>
        </div>
      ) : (
        <button
          className="btn mint"
          disabled={create.isPending}
          onClick={() =>
            create.mutate(undefined, {
              onSuccess: (r) => setLink(r.url),
              onError: () => toast('No se pudo crear el enlace. Revisá el token del bot.'),
            })
          }
        >
          Vincular Telegram
        </button>
      )}
    </section>
  );
}

function EmailCard({ s }: { s: NotificationSettings }) {
  const user = useUser();
  const toast = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [address, setAddress] = useState(() => user.google_email ?? user.email);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const save = useFinancialMutation(notificationsApi.updateSettings, undefined, ['notifications']);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.notifications });

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      toast((err as Error).message);
      await refresh(); // por ejemplo, el código se anuló por demasiados intentos
    } finally {
      setBusy(false);
    }
  };

  const start = (to: string) =>
    run(async () => {
      const r = await notificationsApi.emailStart(to.trim());
      setEditing(false);
      setCode('');
      toast(r.verified ? 'Listo: los avisos te van a llegar por email' : `Te mandamos un código a ${to.trim()}`);
      await refresh();
    });

  const confirmCode = () =>
    run(async () => {
      qc.setQueryData(keys.notifications, await notificationsApi.emailConfirm(code));
      setCode('');
      toast('Email confirmado: los avisos te van a llegar ahí');
    });

  const remove = () =>
    run(async () => {
      await notificationsApi.emailRemove();
      setAddress(user.google_email ?? user.email);
      toast('Ya no vas a recibir avisos por email');
      await refresh();
    });

  const isGoogle = !!user.google_email && address.trim().toLowerCase() === user.google_email;

  let body: JSX.Element;
  if (!s.email_available) {
    body = (
      <p className="hint">
        Para activarlo, configurá una cuenta de correo del servidor en el archivo <code>.env</code> (
        <code>SMTP_USER</code> y <code>SMTP_PASSWORD</code>; con Gmail, una contraseña de aplicación). Los pasos
        están en el README.
      </p>
    );
  } else if (s.email_address && !editing) {
    body = (
      <div className="stack tight">
        <div className="switch-row">
          <div>
            <b>Recibir avisos por email</b>
            <span className="hint">{s.email_address}</span>
          </div>
          <Switch
            checked={s.email_enabled}
            disabled={save.isPending}
            label="Recibir avisos por email"
            onChange={(v) => save.mutate({ email_enabled: v })}
          />
        </div>
        <div className="row-actions start">
          <button
            className="btn small"
            onClick={() => {
              setAddress('');
              setEditing(true);
            }}
          >
            Cambiar dirección
          </button>
          <button className="btn small" disabled={busy} onClick={() => void remove()}>
            Quitar
          </button>
        </div>
      </div>
    );
  } else if (s.email_pending && !editing) {
    const pending = s.email_pending;
    body = (
      <form
        className="form narrow"
        onSubmit={(e) => {
          e.preventDefault();
          if (code.length === 6) void confirmCode();
        }}
      >
        <p className="soft">
          Te mandamos un código de 6 dígitos a <b>{pending}</b>. Escribilo acá; vence en 15 minutos. Si no llega, mirá
          en Spam.
        </p>
        <Field label="Código">
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          />
        </Field>
        <div className="row-actions start">
          <button className="btn mint" disabled={busy || code.length !== 6}>
            Confirmar
          </button>
          <button type="button" className="btn small" disabled={busy} onClick={() => void start(pending)}>
            Reenviar código
          </button>
          <button type="button" className="btn small" onClick={() => setEditing(true)}>
            Usar otra dirección
          </button>
        </div>
      </form>
    );
  } else {
    body = (
      <form
        className="form narrow"
        onSubmit={(e) => {
          e.preventDefault();
          if (emailValid(address)) void start(address);
        }}
      >
        <Field
          label="Email donde recibir los avisos"
          hint={isGoogle ? 'Es el de tu cuenta de Google: se activa sin código.' : 'Te vamos a mandar un código para confirmarlo.'}
        >
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={254}
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
        </Field>
        <div className="row-actions start">
          <button className="btn mint" disabled={busy || !emailValid(address)}>
            {isGoogle ? 'Activar' : 'Enviar código'}
          </button>
          {editing && (
            <button type="button" className="btn small" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          )}
        </div>
      </form>
    );
  }

  return (
    <section className="card">
      <SectionHeader
        title="Email"
        description="Recibí el resumen de vencimientos en tu correo, por ejemplo en tu Gmail. Funciona aunque no tengas HTTPS."
      />
      {body}
    </section>
  );
}

export function NotificationsSection() {
  const toast = useToast();
  const settings = useNotificationSettings();
  const save = useFinancialMutation(notificationsApi.updateSettings, 'Preferencias de avisos guardadas', ['notifications']);
  const test = useFinancialMutation(notificationsApi.test, undefined, ['notifications']);

  if (!settings.data) return <Loading error={settings.error} />;
  const s = settings.data;

  return (
    <div className="stack">
      <section className="card">
        <SectionHeader
          title="Avisos"
          description="Te avisamos de facturas y pagos fijos que vencen, resúmenes de tarjeta, presupuestos al límite y cuando pasás el límite diario."
          action={
            <button
              className="btn"
              disabled={test.isPending}
              onClick={() =>
                test.mutate(undefined, {
                  onSuccess: (r) =>
                    toast(
                      r.push_sent || r.telegram_sent || r.email_sent
                        ? 'Aviso de prueba enviado'
                        : 'No hay dispositivos, Telegram ni email vinculados todavía',
                    ),
                })
              }
            >
              <Icon name="bell" size={18} /> Enviar prueba
            </button>
          }
        />
        <div className="switch-row">
          <div>
            <b>Mandar avisos</b>
            <span className="hint">Un resumen por día y, durante el día, solo lo urgente (vence hoy o venció).</span>
          </div>
          <Switch
            checked={s.notifications_enabled}
            label="Mandar avisos"
            onChange={(v) => save.mutate({ notifications_enabled: v })}
          />
        </div>
        <div className="fgrid">
          <Field label="Hora del resumen diario">
            <select value={s.notify_hour} onChange={(e) => save.mutate({ notify_hour: Number(e.target.value) })}>
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, '0')}:00
                </option>
              ))}
            </select>
          </Field>
          <Field label="Avisar con anticipación">
            <select
              value={s.notify_days_before}
              onChange={(e) => save.mutate({ notify_days_before: Number(e.target.value) })}
            >
              {[0, 1, 2, 3, 5, 7].map((d) => (
                <option key={d} value={d}>
                  {d === 0 ? 'Solo el mismo día' : `${d} día${d === 1 ? '' : 's'} antes`}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </section>
      <PushCard devices={s.push_devices} />
      <TelegramCard linked={s.telegram_linked} available={s.telegram_available} />
      <EmailCard s={s} />
    </div>
  );
}
