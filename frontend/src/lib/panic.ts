import { api } from './api'
import type { PanicContext, PanicEpisodeIn } from './types'

/**
 * File d'attente locale des épisodes, et contexte mis en réserve.
 *
 * Une crise arrive dans le métro. Il n'y a pas de réseau, et il ne doit y avoir
 * **aucune** attente : la séquence tourne entièrement côté client, sur du contenu
 * embarqué dans le bundle. Ce module tient les deux conséquences de ce choix :
 *
 * 1. **Le contexte est mis en réserve à l'ouverture de l'application**, quand le
 *    réseau est là. Il contient l'état personnel (porte du froid validée ou non,
 *    bilan des épisodes passés) — pas le contenu, qui est dans le code.
 * 2. **Un épisode qui n'a pas pu partir est gardé**, puis rejoué au prochain
 *    démarrage. Il est retiré de la file **avant** l'envoi réussi seulement, jamais
 *    avant l'essai : un échec ne doit pas perdre la donnée.
 *
 * Le service worker ne met jamais l'API en cache — sur des données de santé, une
 * valeur périmée est une valeur fausse. Le contexte en réserve est donc daté, et
 * l'interface dit quand il est vieux plutôt que de le faire passer pour frais.
 */

const CONTEXT_KEY = 'fa.panic.context'
const QUEUE_KEY = 'fa.panic.queue'

type StoredContext = { at: number; context: PanicContext }

export function cacheContext(context: PanicContext): void {
  try {
    localStorage.setItem(CONTEXT_KEY, JSON.stringify({ at: Date.now(), context }))
  } catch {
    /* stockage plein ou refusé : on continue sans réserve, ce n'est pas bloquant */
  }
}

export function loadContext(): { context: PanicContext; ageHours: number } | null {
  try {
    const raw = localStorage.getItem(CONTEXT_KEY)
    if (!raw) return null
    const stored = JSON.parse(raw) as StoredContext
    return {
      context: stored.context,
      ageHours: Math.round((Date.now() - stored.at) / 3_600_000),
    }
  } catch {
    return null
  }
}

function readQueue(): PanicEpisodeIn[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    return raw ? (JSON.parse(raw) as PanicEpisodeIn[]) : []
  } catch {
    return []
  }
}

function writeQueue(queue: PanicEpisodeIn[]): void {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
  } catch {
    /* rien à faire de mieux : perdre l'épisode est le pire cas, on l'accepte ici */
  }
}

export function queueSize(): number {
  return readQueue().length
}

/**
 * Envoie un épisode, ou le met en file si l'envoi échoue.
 *
 * Retourne `true` si le serveur l'a bien reçu. Le `false` n'est pas une erreur à
 * afficher comme telle : l'épisode est conservé et repartira. Ce qu'il faut dire à
 * l'utilisateur, c'est « c'est gardé, ça partira », pas « échec ».
 */
export async function sendOrQueue(episode: PanicEpisodeIn): Promise<boolean> {
  try {
    await api.recordPanic(episode)
    return true
  } catch {
    writeQueue([...readQueue(), episode])
    return false
  }
}

/**
 * Rejoue la file. Appelé au démarrage, une fois l'authentification faite.
 *
 * Chaque épisode est retiré **après** son envoi réussi, et ceux qui échouent restent
 * dans la file dans leur ordre d'origine. Un épisode refusé par le serveur avec une
 * erreur définitive (422 : la porte du froid n'est pas validée) resterait en file
 * indéfiniment — on le laisse plutôt que de le supprimer en silence, parce que
 * supprimer une donnée de santé sans le dire est pire qu'une file qui traîne.
 */
export async function flushQueue(): Promise<number> {
  const queue = readQueue()
  if (queue.length === 0) return 0

  const remaining: PanicEpisodeIn[] = []
  let sent = 0
  for (const episode of queue) {
    try {
      await api.recordPanic(episode)
      sent += 1
    } catch {
      remaining.push(episode)
    }
  }
  writeQueue(remaining)
  return sent
}
