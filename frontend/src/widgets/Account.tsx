import { useCallback, useEffect, useState } from 'react'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import { pushState, subscribe, unsubscribe, type PushState } from '../lib/push'
import {
  cancelReminder,
  loadReminder,
  permissionState,
  saveReminder,
  scheduleReminder,
} from '../lib/reminder'
import type { EngineStatus, MemoryStats, PushKey } from '../lib/types'
import { useAuth } from '../state/AuthContext'

/** Le rappel local ne part que si le check-in du jour manque : sinon c'est du bruit. */
const checkinMissing = async () => {
  try {
    return !(await api.thread()).state.checkin_done
  } catch {
    return false
  }
}

export default function Account(_props: WidgetProps) {
  const { user, logout } = useAuth()
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [pushKey, setPushKey] = useState<PushKey | null>(null)
  const [push, setPush] = useState<PushState | null>(null)
  const [time, setTime] = useState(loadReminder().time)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [confirmEmail, setConfirmEmail] = useState('')
  const [askDelete, setAskDelete] = useState(false)

  const refresh = useCallback(async () => {
    const key = await api.pushKey().catch(() => null)
    if (key) {
      setPushKey(key)
      setTime(key.rappel.heure)
    }
    setPush(await pushState())
  }, [])

  useEffect(() => {
    api.engineStatus().then(setEngine).catch(() => undefined)
    api.memory().then((data) => setMemory(data.stats)).catch(() => undefined)
    void refresh()
  }, [refresh])

  const reminderOn = pushKey?.rappel.actif ?? false

  /** Active le rappel : abonnement push si possible, repli local sinon. */
  async function toggleReminder(next: boolean) {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.pushReminder(next, time)
      if (next) {
        const attempt = await subscribe()
        if (attempt.ok) {
          setMessage(`Rappel activé à ${time}, notifications sur cet appareil.`)
        } else {
          // Repli : minuterie dans la page, avec sa limite annoncée.
          const local = { enabled: true, time }
          saveReminder(local)
          if (permissionState() === 'granted') scheduleReminder(local, checkinMissing)
          setMessage(`${attempt.message} Repli sur le rappel local (application ouverte).`)
        }
      } else {
        await unsubscribe()
        cancelReminder()
        saveReminder({ enabled: false, time })
        setMessage('Rappel désactivé.')
      }
      setPushKey((current) => (current ? { ...current, rappel: result.rappel } : current))
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function changeTime(next: string) {
    setTime(next)
    saveReminder({ ...loadReminder(), time: next })
    if (reminderOn) {
      setBusy(true)
      try {
        await api.pushReminder(true, next)
        setMessage(`Heure du rappel : ${next}.`)
      } finally {
        setBusy(false)
      }
    }
  }

  async function testPush() {
    setBusy(true)
    try {
      const result = await api.pushTest()
      setMessage(
        result.envoyes > 0
          ? `Notification envoyée à ${result.envoyes} appareil(s).`
          : "Aucun envoi : vérifie l'abonnement de cet appareil.",
      )
    } catch (exception) {
      setMessage(exception instanceof Error ? exception.message : 'Test impossible.')
    } finally {
      setBusy(false)
    }
  }

  async function exportData() {
    setBusy(true)
    try {
      const data = await api.exportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `fuck-anxiety-${new Date().toISOString().slice(0, 10)}.json`
      link.click()
      URL.revokeObjectURL(url)
      setMessage('Export téléchargé.')
    } finally {
      setBusy(false)
    }
  }

  async function removeAccount() {
    setBusy(true)
    try {
      const result = await api.deleteAccount(confirmEmail)
      const total = Object.values(result.lignes_effacees).reduce((a, b) => a + b, 0)
      setMessage(`Compte supprimé — ${total} lignes effacées.`)
      logout()
    } catch (exception) {
      setMessage(exception instanceof Error ? exception.message : 'Suppression impossible.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="w-body">
      <p className="small">{user?.email}</p>

      <div className="divider" />

      <h4 style={{ marginBottom: 6 }}>Analyse par intelligence artificielle</h4>
      <p style={{ fontSize: '0.875rem', margin: '0 0 6px' }}>
        L'IA est active sur ce compte, et il n'y a pas d'interrupteur pour la couper.
      </p>
      <p className="tiny dim">
        Ce que cela implique : tes données — dont le texte de ton journal — sont envoyées à l'API du
        modèle de langage pour rédiger les réponses et les analyses. Si tu ne veux pas de cet envoi,
        la seule voie est de ne pas écrire ces contenus ici, ou de supprimer ton compte plus bas.
      </p>
      {engine && (
        <p className="tiny dim">
          Moteur : {engine.moteur_principal ?? 'aucun'} · fallback : {engine.fallback ?? 'aucun'} ·
          embeddings : {engine.recherche_vectorielle ? engine.modele_embeddings : 'désactivés'} ·
          mode : <strong>{engine.mode_effectif}</strong>
        </p>
      )}

      <div className="divider" />

      <h4 style={{ marginBottom: 6 }}>Rappel quotidien</h4>
      <label
        style={{ display: 'flex', gap: 12, alignItems: 'center', textTransform: 'none', letterSpacing: 0, fontSize: '0.875rem', fontWeight: 400 }}
      >
        <input
          type="checkbox"
          checked={reminderOn}
          disabled={busy || push?.supported === false}
          onChange={(event) => toggleReminder(event.target.checked)}
        />
        <span>Me rappeler le check-in chaque jour</span>
      </label>
      <div className="row" style={{ marginTop: 'var(--g1)' }}>
        <input
          type="time"
          value={time}
          style={{ width: 150 }}
          disabled={busy}
          onChange={(event) => changeTime(event.target.value)}
        />
        <span className="tiny dim">Heure de ton fuseau ({user?.timezone}), pas celui du serveur.</span>
      </div>

      {push && (
        <p className="tiny dim">
          {push.serverReady
            ? push.subscribed
              ? 'Notifications push actives sur cet appareil : le rappel part même application fermée.'
              : (push.reason ?? "Cet appareil n'est pas encore abonné.")
            : (push.reason ?? 'Push indisponible.')}
        </p>
      )}
      {pushKey && pushKey.appareils.length > 0 && (
        <p className="tiny dim">
          {pushKey.appareils.length} appareil(s) enregistré(s) —{' '}
          {pushKey.appareils.filter((row) => row.actif).length} actif(s).
        </p>
      )}
      <div className="btn-row">
        <button className="btn-sm" disabled={busy || !push?.subscribed} onClick={testPush}>
          Envoyer un test
        </button>
      </div>

      <div className="divider" />

      <h4 style={{ marginBottom: 6 }}>Mémoire</h4>
      {memory ? (
        <>
          <p className="tiny">
            <strong>{memory.total}</strong> souvenir(s) conservé(s), dont{' '}
            <strong>{memory.vectorises}</strong> vectorisé(s) —{' '}
            {memory.par_source.map((row) => `${row.source_kind} ${row.n}`).join(' · ')}
          </p>
          <p className="tiny dim">
            Tout est conservé sans limite d'ancienneté : rien n'est oublié, et les chiffres sont
            recalculés sur l'historique entier plutôt qu'échantillonnés.
          </p>
        </>
      ) : (
        <p className="tiny dim">Chargement…</p>
      )}
      <div className="btn-row">
        <button
          className="btn-sm"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const result = await api.reindexMemory()
              setMemory(result.stats)
              setMessage(`${result.vectorises} souvenir(s) vectorisé(s).`)
            } finally {
              setBusy(false)
            }
          }}
        >
          Réindexer la mémoire
        </button>
      </div>

      <div className="divider" />

      <h4 style={{ marginBottom: 6 }}>Tes données</h4>
      <p className="tiny dim">
        L'export contient tout : check-in, journal, échelles, activités, expositions, analyses, fil
        et mémoire. La suppression est immédiate et irréversible — aucune copie n'est conservée.
      </p>
      <div className="btn-row">
        <button className="btn-sm" disabled={busy} onClick={exportData}>
          Exporter en JSON
        </button>
        <button className="btn-sm" disabled={busy} onClick={() => setAskDelete((value) => !value)}>
          Supprimer mon compte
        </button>
      </div>
      {askDelete && (
        <div style={{ marginTop: 'var(--g2)' }}>
          <label htmlFor="confirm-email">
            Écris ton adresse pour confirmer<span className="hint">{user?.email}</span>
          </label>
          <input
            id="confirm-email"
            value={confirmEmail}
            onChange={(event) => setConfirmEmail(event.target.value)}
          />
          <div className="btn-row">
            <button
              className="btn-primary btn-sm"
              disabled={busy || confirmEmail.trim().toLowerCase() !== (user?.email ?? '').toLowerCase()}
              onClick={removeAccount}
            >
              Supprimer définitivement
            </button>
            <button className="btn-sm" onClick={() => setAskDelete(false)}>
              Annuler
            </button>
          </div>
        </div>
      )}

      {message && <p className="tiny" style={{ marginTop: 'var(--g2)' }}>{message}</p>}

      <div className="divider" />

      <h4 style={{ marginBottom: 6 }}>Limites</h4>
      <ul className="source-list">
        <li>Aucun diagnostic. Le GAD-7 est un outil de dépistage et de suivi.</li>
        <li>Aucun conseil sur les médicaments : ça relève de ton médecin.</li>
        <li>Pas un dispositif médical certifié.</li>
        <li>
          GAD-7 ≥ 15, ou aucune amélioration après 6 à 8 semaines : l'étape suivante recommandée par
          NICE est une TCC accompagnée. Ce n'est pas un échec, c'est la suite prévue.
        </li>
      </ul>
      <p className="tiny">
        Idées suicidaires : <strong>3114</strong> (France, gratuit, 24 h/24), ou <strong>15</strong> /{' '}
        <strong>112</strong>.
      </p>
    </div>
  )
}
