import type { WidgetProps } from '../components/WidgetHost'
import { useAuth } from '../state/AuthContext'

/** Même se déconnecter est un widget : rien ne sort du fil. */
export default function Logout(_props: WidgetProps) {
  const { logout } = useAuth()
  return (
    <>
      <div className="w-body">
        <p className="small">
          Ton fil et tes données restent enregistrés. Tu les retrouves à la prochaine connexion.
        </p>
      </div>
      <div className="w-foot">
        <button className="btn-primary" onClick={logout}>
          Confirmer
        </button>
      </div>
    </>
  )
}
