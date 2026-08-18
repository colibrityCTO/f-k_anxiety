import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // En développement, le front tape sur /api et Vite relaie vers FastAPI :
      // pas de CORS à gérer et une seule origine dans le navigateur.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    // Railway sert le front derrière un domaine généré : on autorise l'hôte.
    allowedHosts: true,
  },
})
