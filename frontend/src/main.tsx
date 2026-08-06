import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/index.css'
import App from './App.tsx'

async function clearLegacyPwaState(): Promise<void> {
  const hadController = 'serviceWorker' in navigator && navigator.serviceWorker.controller !== null

  if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations()
    await Promise.all(registrations.map((registration) => registration.unregister()))
  }

  if ('caches' in window) {
    const cacheNames = await caches.keys()
    await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)))
  }

  // An unregistered worker can still control the current document until the
  // next navigation. Reload exactly once so legacy PWA users move onto Vite's
  // current hashed assets instead of the retired offline shell.
  if (hadController && sessionStorage.getItem('fitpath-pwa-migrated') !== '1') {
    sessionStorage.setItem('fitpath-pwa-migrated', '1')
    window.location.reload()
  }
}

void clearLegacyPwaState().catch((error: unknown) => {
  console.warn('FitPath could not clear the retired offline cache.', error)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
