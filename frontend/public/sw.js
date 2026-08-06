/*
 * FitPath legacy PWA retirement worker.
 *
 * Earlier versions installed an offline-first service worker that can keep
 * serving the retired UI after a new deployment. Browsers with that worker
 * registered will update to this script, delete the old caches, unregister
 * the worker, and reload open FitPath tabs onto the current Vite build.
 */

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys()
      await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)))
      await self.registration.unregister()

      const windows = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      })
      await Promise.all(windows.map((client) => client.navigate(client.url)))
    })(),
  )
})

