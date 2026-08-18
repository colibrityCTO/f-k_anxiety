/**
 * Service worker : coque hors-ligne, rien de plus.
 *
 * Deux stratégies, et une règle absolue.
 *
 * - Les fichiers de l'application (HTML, JS, CSS, icônes) : réseau d'abord, cache
 *   en repli. Tu gardes une application qui s'ouvre sans connexion.
 * - L'API : **jamais** de cache. Servir un vieux check-in ou une vieille analyse
 *   depuis le cache serait pire que d'afficher une erreur — sur des données de
 *   santé, une valeur périmée est une valeur fausse.
 */

const CACHE = 'fa-shell-v1'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  // Données personnelles : on ne met jamais l'API en cache.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/chat/')) return
  if (url.origin !== self.location.origin) return

  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone()
        caches.open(CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined)
        return response
      })
      .catch(() =>
        caches.match(request).then((cached) => cached ?? caches.match('/index.html')),
      ),
  )
})

/**
 * Notification push : c'est le service de push du navigateur qui réveille ce
 * worker, application fermée. Sans ce gestionnaire, rien ne s'affiche.
 */
self.addEventListener('push', (event) => {
  let payload = { title: 'FUCK ANXIETY', body: 'Rappel.', url: '/', tag: 'fa' }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch {
    if (event.data) payload.body = event.data.text()
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: payload.tag,
      data: { url: payload.url },
      requireInteraction: false,
    }),
  )
})

/** Rappel quotidien : le clic ramène dans le fil. */
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clients) => {
      const open = clients.find((client) => client.url.includes(self.location.origin))
      if (open) return open.focus()
      return self.clients.openWindow('/')
    }),
  )
})
