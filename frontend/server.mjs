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

const PORT = Number(process.env.PORT || 8080)
const HOST = process.env.HOST || '0.0.0.0'
const ROOT = resolve(process.env.STATIC_DIR || './dist')

/**
 * Analyse `API_ORIGIN` **une fois**, au démarrage.
 *
 * Deux raisons. D'abord le schéma : `API_ORIGIN=exemple.up.railway.app` est la
 * faute de saisie la plus naturelle, et `new URL()` la refuse — on ajoute donc
 * `https://` plutôt que de faire échouer la configuration pour un détail.
 * Ensuite l'isolement : analyser à chaque requête faisait remonter un
 * `TypeError: Invalid URL` depuis le gestionnaire, ce qui **tuait le processus**.
 * Une variable mal renseignée doit dégrader le service, pas l'arrêter.
 */
function parseOrigin(raw) {
  const value = (raw || '').trim().replace(/\/+$/, '')
  if (!value) return { target: null, origin: '', reason: 'API_ORIGIN non définie' }

  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`
  try {
    const target = new URL(candidate)
    if (!/^https?:$/.test(target.protocol)) {
      return { target: null, origin: value, reason: `schéma non géré : ${target.protocol}` }
    }
    return {
      target,
      origin: candidate,
      reason: null,
      corrected: candidate !== value ? `schéma ajouté : ${candidate}` : null,
    }
  } catch (error) {
    return { target: null, origin: value, reason: `URL invalide (${error.message})` }
  }
}

const API = parseOrigin(process.env.API_ORIGIN)
const API_ORIGIN = API.origin

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
  if (!API.target) {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(
      JSON.stringify({
        detail:
          `Le relais vers l'API n'est pas utilisable : ${API.reason}. Corrige la variable ` +
          `API_ORIGIN du service front (exemple : https://mon-api.up.railway.app).`,
        api_origin: API_ORIGIN || null,
      }),
    )
    return
  }

  const target = API.target
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
      const status = upstreamRes.statusCode || 502
      const type = String(upstreamRes.headers['content-type'] || '')

      /*
       * Une erreur 5xx qui n'est pas du JSON ne vient pas de l'API : c'est la
       * page d'erreur de l'hébergeur, servie quand le service ne répond pas.
       * Transmise telle quelle, elle arrive au front sous forme de HTML que le
       * client n'arrive pas à lire, et l'utilisateur voit « Erreur 502 » sans
       * savoir quoi corriger. On la remplace par un message actionnable.
       */
      if (status >= 500 && !type.includes('json')) {
        upstreamRes.resume() // on vide le flux sans le lire
        res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
        res.end(
          JSON.stringify({
            detail:
              `L'API a répondu ${status} sans contenu JSON : ce n'est pas elle qui parle, mais ` +
              `l'hébergeur. Vérifie que le service backend est en ligne et que API_ORIGIN pointe ` +
              `dessus (actuellement ${API_ORIGIN}).`,
            upstream_status: status,
            api_origin: API_ORIGIN,
          }),
        )
        return
      }

      res.writeHead(status, upstreamRes.headers)
      upstreamRes.pipe(res)
    },
  )

  upstream.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(
      JSON.stringify({
        detail: `Backend injoignable depuis le front : ${error.message}`,
        api_origin: API_ORIGIN,
      }),
    )
  })

  req.pipe(upstream)
}

/** Interroge `API_ORIGIN/health` et rapporte le résultat brut, sans l'interpréter. */
function checkApi() {
  return new Promise((resolve) => {
    if (!API.target) return resolve({ ok: false, erreur: API.reason })

    const target = API.target
    const send = target.protocol === 'https:' ? httpsRequest : httpRequest
    const started = Date.now()
    const upstream = send(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || (target.protocol === 'https:' ? 443 : 80),
        method: 'GET',
        path: (target.pathname === '/' ? '' : target.pathname) + '/health',
        headers: { host: target.host, accept: 'application/json' },
        timeout: 5000,
      },
      (upstreamRes) => {
        let body = ''
        upstreamRes.setEncoding('utf8')
        upstreamRes.on('data', (chunk) => {
          if (body.length < 2000) body += chunk
        })
        upstreamRes.on('end', () => {
          let parsed = null
          try {
            parsed = JSON.parse(body)
          } catch {
            parsed = { brut: body.slice(0, 200) }
          }
          resolve({
            ok: (upstreamRes.statusCode || 0) < 400,
            statut: upstreamRes.statusCode,
            ms: Date.now() - started,
            reponse: parsed,
          })
        })
      },
    )
    upstream.on('timeout', () => {
      upstream.destroy()
      resolve({ ok: false, erreur: 'délai dépassé (5 s)' })
    })
    upstream.on('error', (error) => resolve({ ok: false, erreur: error.message }))
    upstream.end()
  })
}

/*
 * Tout le gestionnaire est sous filet. Une exception synchrone ici ferait tomber
 * le processus entier, et l'hébergeur répondrait 502 sur *toutes* les routes —
 * y compris les fichiers statiques, qui n'ont rien à voir. Un bug doit coûter
 * une requête, pas le service.
 */
const server = createServer((req, res) => {
  try {
    handle(req, res)
  } catch (error) {
    console.error('Requête en échec :', error)
    if (!res.headersSent) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify({ detail: `Erreur interne du serveur front : ${error.message}` }))
    } else {
      res.destroy()
    }
  }
})

function handle(req, res) {
  // Un pourcentage isolé dans l'URL (« /%ok ») fait lever decodeURIComponent :
  // on retombe sur le chemin brut plutôt que d'échouer.
  const raw = (req.url || '/').split('?')[0]
  let pathname = raw
  try {
    pathname = decodeURIComponent(raw)
  } catch {
    pathname = raw
  }

  /*
   * `/healthz` sert deux usages. Sans paramètre : la vivacité, pour le
   * healthcheck de l'hébergeur. Avec `?deep=1` : il interroge réellement l'API
   * et renvoie ce qu'elle répond — de quoi savoir en une requête si le problème
   * est le front, la variable API_ORIGIN, ou le backend.
   */
  if (pathname === '/healthz') {
    if (!(req.url || '').includes('deep')) {
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' })
      res.end('ok')
      return
    }
    checkApi().then((api) => {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(
        JSON.stringify(
          {
            front: 'ok',
            serveur: 'server.mjs',
            api_origin: API_ORIGIN || null,
            api_origin_utilisable: Boolean(API.target),
            api_origin_corrige: API.corrected ?? null,
            api,
            diagnostic: !API.target
              ? `API_ORIGIN inutilisable — ${API.reason}. Corrige-la dans les variables du service front.`
              : api.ok
                ? null
                : `Le front ne joint pas l'API : ${api.erreur ?? `réponse ${api.statut}`}.`,
          },
          null,
          2,
        ),
      )
    })
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
