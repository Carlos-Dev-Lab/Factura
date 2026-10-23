import { notificationsApi } from '../api/endpoints';

/** Las notificaciones y el service worker necesitan HTTPS (o localhost). */
export const pushSupported = () =>
  typeof window !== 'undefined' &&
  window.isSecureContext &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  'Notification' in window;

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}

function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (base64url.length % 4)) % 4);
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

/** Nombre corto del dispositivo, para reconocerlo en la lista ("Android · Chrome"). */
function deviceLabel(): string {
  const ua = navigator.userAgent;
  const os = /Android/.test(ua)
    ? 'Android'
    : /iPhone|iPad/.test(ua)
      ? 'iPhone'
      : /Windows/.test(ua)
        ? 'Windows'
        : /Mac/.test(ua)
          ? 'Mac'
          : 'Linux';
  const browser = /Edg\//.test(ua) ? 'Edge' : /Firefox/.test(ua) ? 'Firefox' : /Chrome/.test(ua) ? 'Chrome' : 'Safari';
  return `${os} · ${browser}`;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return (await reg?.pushManager.getSubscription()) ?? null;
}

export type PushResult = 'enabled' | 'denied' | 'unsupported';

export async function enablePush(): Promise<PushResult> {
  if (!pushSupported()) return 'unsupported';
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return 'denied';
  const reg = await navigator.serviceWorker.register('/sw.js');
  await navigator.serviceWorker.ready;
  const { public_key } = await notificationsApi.pushKey();
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) }));
  await notificationsApi.subscribe(sub.toJSON(), deviceLabel());
  return 'enabled';
}

export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  await notificationsApi.unsubscribe(sub.endpoint).catch(() => undefined);
  await sub.unsubscribe();
}

/**
 * Al cerrar sesión: este dispositivo deja de recibir los avisos de la cuenta (si no, en un celular o
 * una compu compartida seguirían llegando notificaciones con montos y proveedores de quien salió) y
 * se descarta un archivo compartido que haya quedado sin abrir.
 */
export async function forgetThisDevice(): Promise<void> {
  await disablePush().catch(() => undefined);
  if ('caches' in window) await caches.delete('factura-share').catch(() => false);
}

/**
 * Al entrar: si el navegador ya estaba suscripto (por ejemplo, la sesión de otra persona venció sin
 * cerrarla), la suscripción pasa a la cuenta que acaba de entrar. Un dispositivo nunca recibe avisos
 * de una cuenta distinta de la que lo está usando.
 */
export async function claimThisDevice(): Promise<void> {
  const sub = await currentSubscription().catch(() => null);
  if (sub) await notificationsApi.subscribe(sub.toJSON(), deviceLabel()).catch(() => undefined);
}

/** Archivo que llegó con "Compartir → Factura" desde otra app (lo guarda el service worker). */
export async function takeSharedFile(): Promise<File | null> {
  const url = new URL(window.location.href);
  if (!url.searchParams.has('compartido') || !('caches' in window)) return null;
  url.searchParams.delete('compartido');
  window.history.replaceState(null, '', url.pathname + url.search);
  const cache = await caches.open('factura-share');
  const response = await cache.match('/shared-file');
  if (!response) return null;
  await cache.delete('/shared-file');
  const name = decodeURIComponent(response.headers.get('X-File-Name') ?? 'compartido');
  const blob = await response.blob();
  return new File([blob], name, { type: blob.type });
}
