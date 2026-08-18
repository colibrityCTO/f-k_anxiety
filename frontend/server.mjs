/**
 * Serveur de production du front : fichiers statiques + relais /api.
 *
 * Deux raisons de ne pas utiliser `vite preview` en production :
 *
 * 1. Il exige les dépendances de développement dans l'image finale — Vite,
 *    esbuild, TypeScript — pour servir des fichiers déjà compilés.
 * 2. L'URL de l'API serait figée au moment du build (`VITE_API_URL` est inlinée
 *    par Vite). Changer de backend obligerait à reconstruire.
 *
 * Ici le front appelle toujours `/api`, et ce serveur relaie vers `API_ORIGIN`,
 * une variable lue **au démarrage**. Même origine pour le navigateur : pas de
 * CORS, pas de préflight, et l'URL du backend se change sans rebuild.
 *
 * Aucune dépendance : uniquement les modules natifs de Node.
 */

import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer, request as httpRequest } from 'node:http'
import { request as httpsRequest } from 'node:https'
import { extname, join, normalize, resolve } from 'node:path'

const PORT = Number(process.env.PORT || 4173)
const HOST = process.env.HOST || '0.0.0.0'
const ROOT = resolve(process.env.STATIC_DIR || './dist')
const API_ORIGIN = (process.env.API_ORIGIN || '').replace(/\/+$/, '')

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
}

/**
 * Les fichiers d'`assets/` portent un hachage dans leur nom : ils peuvent être
 * mis en cache un an. `index.html` et `sw.js` ne doivent **jamais** l'être — un
 * service worker figé dans un cache épinglerait l'ancienne application.
 */
function cacheHeader(pathname) {
  if (pathname.startsWith('/assets/')) return 'public, max-age=31536000, immutable'
  if (pathname === '/sw.js' || pathname.endsWith('.html') || pathname === '/') return 'no-store'
  return 'public, max-age=3600'
}

function serveFile(res, filePath, pathname, statusCode = 200) {
  const type = TYPES[extname(filePath).toLowerCase()] || 'application/octet-stream'
  res.writeHead(statusCode, {
    'Content-Type': type,
    'Cache-Control': cacheHeader(pathname),
    'X-Content-Type-Options': 'nosniff',
    // Le service worker doit pouvoir contrôler toute l'origine.
    ...(pathname === '/sw.js' ? { 'Service-Worker-Allowed': '/' } : {}),
  })
  createReadStream(filePath).pipe(res)
}

/** Relais transparent vers l'API. Le flux SSE passe sans être tamponné. */
function proxy(req, res) {
  if (!API_ORIGIN) {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(
      JSON.stringify({
        detail:
          "API_ORIGIN n'est pas configurée sur le service front : impossible de joindre le backend.",
      }),
    )
    return
  }

  const target = new URL(API_ORIGIN)
  const send = target.protocol === 'https:' ? httpsRequest : httpRequest
  const upstreamPath = req.url.replace(/^\/api/, '') || '/'

  const upstream = send(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      method: req.method,
      path: (target.pathname === '/' ? '' : target.pathname) + upstreamPath,
      headers: { ...req.headers, host: target.host },
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers)
      upstreamRes.pipe(res)
    },
  )

  upstream.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify({ detail: `Backend injoignable : ${error.message}` }))
  })

  req.pipe(upstream)
}

const server = createServer((req, res) => {
  const pathname = decodeURIComponent((req.url || '/').split('?')[0])

  if (pathname === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end('ok')
    return
  }

  if (pathname.startsWith('/api')) {
    proxy(req, res)
    return
  }

  // `normalize` neutralise les tentatives de remontée hors du dossier servi.
  const candidate = join(ROOT, normalize(pathname).replace(/^(\.\.[/\\])+/, ''))
  if (candidate.startsWith(ROOT) && existsSync(candidate) && statSync(candidate).isFile()) {
    serveFile(res, candidate, pathname)
    return
  }

  // Application à écran unique : toute autre route renvoie l'index.
  const index = join(ROOT, 'index.html')
  if (existsSync(index)) {
    serveFile(res, index, '/index.html')
    return
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end('dist/index.html introuvable — le build a-t-il tourné ?')
})

server.listen(PORT, HOST, () => {
  console.log(
    `Front servi sur http://${HOST}:${PORT} — dossier ${ROOT} · /api → ${API_ORIGIN || '(non configurée)'}`,
  )
})
