/* Service worker de Factura: notificaciones push, "Compartir → Factura" y caché de la app.
 *
 * - Las respuestas de la API nunca se guardan en caché (tienen datos privados).
 * - Los archivos de /assets/ tienen un hash en el nombre: se guardan y se sirven desde caché.
 * - Las páginas se piden siempre a la red; sin conexión se muestra la última versión guardada.
 */
const ASSETS = 'factura-assets-v1';
const PAGES = 'factura-pages-v1';
const SHARE = 'factura-share';
const KEEP = [ASSETS, PAGES, SHARE];

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((n) => !KEEP.includes(n)).map((n) => caches.delete(n)));
      await self.clients.claim();
    })(),
  );
});

async function handleShare(request) {
  const form = await request.formData();
  const file = form.get('file');
  if (file && typeof file !== 'string') {
    const cache = await caches.open(SHARE);
    await cache.put(
      '/shared-file',
      new Response(file, {
        headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) },
      }),
    );
  }
  return Response.redirect('/facturas?compartido=1', 303);
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSETS);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function networkFirstPage(request) {
  const cache = await caches.open(PAGES);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put('/', response.clone());
    return response;
  } catch {
    return (await cache.match('/')) || Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.method === 'POST' && url.pathname === '/share-target') {
    event.respondWith(handleShare(request));
    return;
  }
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/assets/')) event.respondWith(cacheFirst(request));
  else if (request.mode === 'navigate') event.respondWith(networkFirstPage(request));
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'Factura', {
      body: data.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: data.tag || 'factura',
      data: { url: data.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin);
  // Solo se abren páginas de la propia app.
  const url = target.origin === self.location.origin ? target.href : self.location.origin;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin);
      if (open) {
        await open.focus();
        return open.navigate(url);
      }
      return self.clients.openWindow(url);
    })(),
  );
});
