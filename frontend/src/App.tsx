import Auth from './screens/Auth'
import Chat from './screens/Chat'
import { useAuth } from './state/AuthContext'

/**
 * Deux écrans en tout. La connexion, puis le fil.
 *
 * Pas de routeur : il n'y a rien à router. Tout ce que fait l'application se
 * passe dans le fil, sous forme de message ou de widget.
 */
export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <p className="spinner">Vérification de la session…</p>
  return user ? <Chat /> : <Auth />
}
