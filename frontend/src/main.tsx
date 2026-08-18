import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { AuthProvider } from './state/AuthContext'
import './styles.css'

// Pas de routeur : l'application est un fil unique. Il n'y a rien à router.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)

// Service worker : uniquement en production. En développement il masquerait les
// modifications derrière son cache, ce qui coûte plus de temps qu'il n'en fait
// gagner.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}
