/**
 * Abonnement aux notifications push.
 *
 * Trois conditions doivent être réunies, et l'interface dit laquelle manque :
 * un service worker enregistré, une autorisation accordée, et une paire de clés
 * VAPID côté serveur. Sans les trois, on retombe sur le rappel local — qui ne
 * survit pas à la fermeture de l'application, et l'annonce.
 *
 * En développement, le service worker n'est pas enregistré (il masquerait les
 * modifications derrière son cache) : le push ne se teste donc qu'en build de
 * production, servi en HTTPS ou sur localhost.
 */

import { api } from './api'

export type PushState = {
  supported: boolean
  serverReady: boolean
  permission: NotificationPermission | 'unsupported'
  subscribed: boolean
  reason: string | null
}

function supported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/**
 * Convertit la clé publique base64url en octets pour PushManager.
 *
 * Le tableau est alloué sur un `ArrayBuffer` explicite : `applicationServerKey`
 * n'accepte pas un `Uint8Array` dont le tampon pourrait être partagé.
 */
function decodeKey(base64: string): ArrayBuffer {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4))
    .replace(/-/g, '+')
    .replace(/_/g, '/')
  const raw = atob(padded)
  const buffer = new ArrayBuffer(raw.length)
  const view = new Uint8Array(buffer)
  for (let index = 0; index < raw.length; index += 1) view[index] = raw.charCodeAt(index)
  return buffer
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  return (await navigator.serviceWorker.getRegistration()) ?? null
}

export async function pushState(): Promise<PushState> {
  if (!supported()) {
    return {
      supported: false,
      serverReady: false,
      permission: 'unsupported',
      subscribed: false,
      reason: 'Ce navigateur ne gère pas les notifications push.',
    }
  }

  const key = await api.pushKey().catch(() => null)
  const registered = await registration()
  const existing = registered ? await registered.pushManager.getSubscription() : null

  return {
    supported: true,
    serverReady: Boolean(key?.disponible),
    permission: Notification.permission,
    subscribed: Boolean(existing),
    reason: !key?.disponible
      ? "Aucune clé VAPID configurée sur le serveur : le push est indisponible."
      : !registered
        ? "Service worker non enregistré : le push ne fonctionne qu'en version compilée (npm run build)."
        : Notification.permission === 'denied'
          ? 'Notifications refusées par le navigateur.'
          : null,
  }
}

/** Abonne l'appareil et enregistre l'abonnement côté serveur. */
export async function subscribe(): Promise<{ ok: boolean; message: string }> {
  if (!supported()) return { ok: false, message: 'Notifications non supportées ici.' }

  const key = await api.pushKey()
  if (!key.disponible || !key.cle_publique) {
    return { ok: false, message: "Le serveur n'a pas de clé VAPID : push impossible." }
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    return { ok: false, message: 'Autorisation refusée par le navigateur.' }
  }

  const registered = await registration()
  if (!registered) {
    return {
      ok: false,
      message: "Service worker absent : le push ne marche qu'en version compilée.",
    }
  }

  const existing = await registered.pushManager.getSubscription()
  const subscription =
    existing ??
    (await registered.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeKey(key.cle_publique),
    }))

  const json = subscription.toJSON() as { endpoint?: string; keys?: Record<string, string> }
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    return { ok: false, message: 'Abonnement incomplet renvoyé par le navigateur.' }
  }

  await api.pushSubscribe({
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
    user_agent: navigator.userAgent.slice(0, 300),
  })
  return { ok: true, message: 'Appareil abonné.' }
}

export async function unsubscribe(): Promise<{ ok: boolean; message: string }> {
  const registered = await registration()
  const subscription = registered ? await registered.pushManager.getSubscription() : null
  if (!subscription) return { ok: true, message: 'Aucun abonnement sur cet appareil.' }

  const json = subscription.toJSON() as { endpoint?: string; keys?: Record<string, string> }
  await subscription.unsubscribe().catch(() => undefined)
  if (json.endpoint) {
    await api
      .pushUnsubscribe({
        endpoint: json.endpoint,
        p256dh: json.keys?.p256dh ?? '',
        auth: json.keys?.auth ?? '',
      })
      .catch(() => undefined)
  }
  return { ok: true, message: 'Appareil désabonné.' }
}
