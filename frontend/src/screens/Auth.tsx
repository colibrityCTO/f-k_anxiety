import { useState } from 'react'
import { useAuth } from '../state/AuthContext'

/**
 * Le seul écran hors du fil.
 *
 * Un mot de passe ne doit jamais transiter dans une conversation : il resterait
 * dans l'historique, dans les journaux du serveur, et pourrait partir vers l'API
 * du modèle. C'est la seule raison pour laquelle cet écran existe.
 *
 * Pas de formulaire d'inscription en plusieurs étapes : e-mail, mot de passe, et
 * l'assistant fait le reste dans le fil.
 */
export default function Auth() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password)
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Échec.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <h1>
        Fuck
        <br />
        Anxiety
      </h1>

      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="email">Adresse e-mail</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">
            Mot de passe
            {mode === 'register' && <span className="hint">10 caractères minimum</span>}
          </label>
          <input
            id="password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={mode === 'register' ? 10 : undefined}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && <p className="error-text">{error}</p>}

        <button className="btn-primary btn-block" type="submit" disabled={busy}>
          {busy ? '…' : mode === 'login' ? 'Entrer' : 'Créer mon compte'}
        </button>

        <div className="btn-row">
          <button
            type="button"
            className="btn-sm"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError(null)
            }}
          >
            {mode === 'login' ? 'Créer un compte' : "J'ai déjà un compte"}
          </button>
        </div>
      </form>

      <p className="tiny dim" style={{ marginTop: 'var(--g4)', maxWidth: '52ch' }}>
        Auto-assistance structurée fondée sur le Protocole Unifié et les recommandations NICE. Pas
        de diagnostic, pas de conseil sur les médicaments, pas un dispositif médical. Idées
        suicidaires : 3114 (France, gratuit, 24 h/24), ou 15 / 112.
      </p>
    </div>
  )
}
