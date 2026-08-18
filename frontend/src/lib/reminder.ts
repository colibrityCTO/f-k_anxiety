/**
 * Rappel quotidien.
 *
 * Ce que ça fait : quand l'application est ouverte (onglet, ou installée sur
 * l'écran d'accueil), une notification part à l'heure choisie si le check-in du
 * jour manque encore.
 *
 * Ce que ça ne fait pas, et il faut le savoir : sans notification **push**
 * serveur, rien ne peut réveiller l'application quand elle est complètement
 * fermée. Un vrai rappel à 21 h même app fermée demande une clé VAPID et un
 * service de push. Tant que ce n'est pas en place, ce rappel n'est fiable que si
 * l'application est installée et reste en arrière-plan.
 *
 * Le compromis assumé : au premier lancement de la journée, si le check-in de la
 * veille manque, l'application le dit dans le fil. Une relance qui dépend de ton
 * ouverture est moins efficace qu'un push — mais elle ne ment pas sur ce qu'elle
 * est.
 */

const KEY = 'fa.reminder'

export type Reminder = { enabled: boolean; time: string }

export function loadReminder(): Reminder {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw) as Reminder
  } catch {
    /* stockage indisponible : on retombe sur le défaut */
  }
  return { enabled: false, time: '21:00' }
}

export function saveReminder(reminder: Reminder): void {
  localStorage.setItem(KEY, JSON.stringify(reminder))
}

export async function askPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) return 'denied'
  if (Notification.permission !== 'default') return Notification.permission
  return Notification.requestPermission()
}

export function permissionState(): NotificationPermission | 'unsupported' {
  if (!('Notification' in window)) return 'unsupported'
  return Notification.permission
}

let handle: number | null = null

/**
 * Programme la prochaine notification. Réarme à chaque déclenchement, et ne
 * notifie que si le check-in du jour manque encore — sinon c'est du bruit.
 */
export function scheduleReminder(
  reminder: Reminder,
  isCheckinMissing: () => Promise<boolean> | boolean,
): void {
  if (handle !== null) {
    window.clearTimeout(handle)
    handle = null
  }
  if (!reminder.enabled || permissionState() !== 'granted') return

  const [hours, minutes] = reminder.time.split(':').map(Number)
  const next = new Date()
  next.setHours(hours, minutes ?? 0, 0, 0)
  if (next.getTime() <= Date.now()) next.setDate(next.getDate() + 1)

  handle = window.setTimeout(
    async () => {
      try {
        if (await isCheckinMissing()) {
          new Notification('FUCK ANXIETY', {
            body: "T'as pas fait ton check-in aujourd'hui. Deux minutes.",
            icon: '/icon-192.png',
            badge: '/icon-192.png',
            tag: 'fa-checkin',
          })
        }
      } finally {
        scheduleReminder(reminder, isCheckinMissing)
      }
    },
    next.getTime() - Date.now(),
  )
}

export function cancelReminder(): void {
  if (handle !== null) {
    window.clearTimeout(handle)
    handle = null
  }
}
