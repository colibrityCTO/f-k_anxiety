import { useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon'
import { api } from '../lib/api'
import type { DayState } from '../lib/types'
import { useAuth } from '../state/AuthContext'
import Account from '../widgets/Account'

/**
 * La page Compte — la seule page de l'application, avec l'écran de crise.
 *
 * ## Pourquoi une page, alors que le principe est « tout dans le fil »
 *
 * Le `README` dit : « Pas de navigation, pas d'onglets, pas de pages. » Cette page
 * est la seconde exception, après QUICK CHILL. Elle se motive autrement, et il vaut
 * mieux le dire que faire comme si la règle tenait encore :
 *
 * - **Les réglages ne sont pas un événement.** Changer son heure de rappel n'a rien à
 *   faire dans un journal de santé — c'est exactement le raisonnement qui a rendu le
 *   widget `account` éphémère.
 * - Un éphémère n'était qu'un demi-remède : le widget quittait le fil, mais il fallait
 *   toujours ouvrir le `+`, trouver une tuile parmi dix-sept, puis faire défiler.
 * - La suppression de compte et l'export ne se cherchent pas dans une grille.
 *
 * La règle devient donc : **le suivi se passe dans le fil ; la crise et
 * l'administration en sortent.**
 *
 * ## Deux détails qui font la différence entre un panneau et une page
 *
 * `history.pushState` à l'ouverture et fermeture sur `popstate` : sans ça, le bouton
 * retour d'Android quitte l'application au lieu de refermer la page. C'est le défaut
 * classique des panneaux plein écran dans une PWA.
 *
 * Le fil n'est pas démonté — on superpose. Revenir doit retrouver la position de
 * lecture exacte, et `Chat` a déjà tout ce qu'il faut pour ça.
 *
 * Le corps des réglages existants n'est pas réécrit : `<Account />` est rendu tel
 * quel. Dupliquer la logique de push, d'export et de suppression pour la mettre dans
 * une page aurait créé deux versions à maintenir, dont une finirait périmée.
 */
export default function Compte({ onClose }: { onClose: () => void }) {
  const { user, logout, refresh } = useAuth()
  const [state, setState] = useState<DayState | null>(null)
  const [name, setName] = useState(user?.display_name ?? '')
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    api
      .thread()
      .then((thread) => setState(thread.state))
      .catch(() => undefined)
  }, [])

  /**
   * Le retour du navigateur referme la page. Sans cette entrée d'historique, il
   * quitterait l'application — sur Android c'est le geste de navigation principal.
   *
   * `onClose` passe par une référence, et l'effet ne dépend de rien. Ce n'est pas un
   * détail de style : l'appelant passe une fonction fléchée recréée à chaque rendu,
   * donc un effet qui en dépend se rejoue, et son nettoyage appelle `history.back()`
   * — la page se refermait instantanément à l'ouverture.
   */
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    // Poussée **conditionnelle**. En développement, StrictMode rejoue les effets
    // (montage → effet → nettoyage → effet) : pousser sans condition créerait deux
    // entrées d'historique, et un seul retour ne refermerait plus la page.
    if (!window.history.state?.compte) window.history.pushState({ compte: true }, '')

    const back = () => close.current()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') dismiss()
    }
    window.addEventListener('popstate', back)
    window.addEventListener('keydown', onKey)
    // Le nettoyage n'a **aucun** effet de bord : c'est ce qui manquait. La version
    // précédente appelait `history.back()` ici, et le nettoyage simulé de StrictMode
    // refermait donc la page dans l'instant qui suivait son ouverture.
    return () => {
      window.removeEventListener('popstate', back)
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  /**
   * Fermer, toujours par le même chemin. Le bouton et Échap font revenir en arrière
   * dans l'historique ; c'est `popstate` qui referme réellement. Un seul chemin
   * signifie qu'on ne peut pas laisser une entrée orpheline derrière soi.
   */
  function dismiss() {
    if (window.history.state?.compte) window.history.back()
    else close.current()
  }

  const profile = (user?.profile ?? {}) as Record<string, unknown>
  const consents = (profile.consentements ?? {}) as Record<string, unknown>
  const onboarding = profile.onboarding as Record<string, unknown> | undefined

  async function saveName() {
    setSaving(true)
    setNote(null)
    try {
      await api.updateMe({ display_name: name.trim() || null })
      await refresh()
      setNote('Nom enregistré.')
    } catch (exception) {
      setNote(exception instanceof Error ? exception.message : 'Enregistrement impossible.')
    } finally {
      setSaving(false)
    }
  }

  async function setCohortConsent(next: boolean) {
    setSaving(true)
    setNote(null)
    try {
      await api.updateMe({
        profile: {
          ...profile,
          consentements: {
            ...consents,
            cohorte: next,
            cohorte_le: new Date().toISOString().slice(0, 10),
          },
        } as Record<string, unknown>,
      })
      await refresh()
      setNote(
        next
          ? 'Contribution activée. Aucune statistique collective ne sera affichée avant qu’il y ait assez de monde.'
          : 'Contribution désactivée. Rien ne change au reste de l’application.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page" role="dialog" aria-modal="true" aria-label="Compte">
      <div className="page-top">
        <span className="page-title">Compte</span>
        <button className="iconbtn" aria-label="Fermer" onClick={dismiss}>
          <Icon name="close" />
        </button>
      </div>

      <div className="page-body">
        {/* --- Identité ---------------------------------------------------- */}
        <h4 style={{ marginBottom: 6 }}>Toi</h4>
        <p className="tiny dim">
          {user?.email}
          {user?.created_at ? ` · compte créé le ${user.created_at.slice(0, 10)}` : ''} ·
          fuseau {user?.timezone}
        </p>
        <div className="field">
          <label htmlFor="compte-nom">
            Comment je t'appelle<span className="hint">Facultatif</span>
          </label>
          <input
            id="compte-nom"
            value={name}
            placeholder="ton prénom"
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="btn-row">
          <button className="btn-sm" disabled={saving} onClick={saveName}>
            Enregistrer
          </button>
        </div>

        <div className="divider" />

        {/* --- Programme --------------------------------------------------- */}
        <h4 style={{ marginBottom: 6 }}>Où tu en es</h4>
        {state ? (
          <>
            <div className="sum">
              <div>
                <span>Semaine</span>
                <b>{state.week}</b>
              </div>
              <div>
                <span>Module</span>
                <b>{state.module}</b>
              </div>
              <div>
                <span>Régime</span>
                <b>{state.status}</b>
              </div>
              <div>
                <span>GAD-7</span>
                <b>{state.gad7_last ?? '—'}</b>
              </div>
            </div>
            <p className="tiny dim">{state.module_title} — {state.module_goal}</p>
            {/* Le critère de sortie est affiché en entier, y compris ce qui n'est pas
                atteint : un critère qu'on ne peut pas vérifier soi-même peut être
                déplacé sans qu'on le voie. */}
            {state.critere && (
              <p className="tiny">
                Critère de sortie — GAD-7 ≤ 5 sur 4 mesures :{' '}
                <b>{state.critere.gad7_ok ? 'atteint' : 'pas encore'}</b> · expositions
                toutes maîtrisées :{' '}
                <b>
                  {state.critere.expositions_ok
                    ? 'atteint'
                    : `${state.critere.expositions_restantes ?? '?'} restante(s)`}
                </b>
              </p>
            )}
          </>
        ) : (
          <p className="tiny dim">Chargement…</p>
        )}

        <div className="divider" />

        {/* --- Portes de sécurité ------------------------------------------ */}
        <h4 style={{ marginBottom: 6 }}>Contre-indications validées</h4>
        <p className="tiny dim">
          Deux exercices ne conviennent pas à tout le monde. Ta confirmation est datée
          et conservée — c'est elle que l'API vérifie avant d'enregistrer.
        </p>
        <p className="tiny">
          Exercices intéroceptifs :{' '}
          <b>
            {typeof profile.interoceptif_valide_le === 'string'
              ? `confirmé le ${profile.interoceptif_valide_le}`
              : 'pas encore confirmé'}
          </b>
          <br />
          Froid sur le visage :{' '}
          <b>
            {typeof profile.froid_valide_le === 'string'
              ? `confirmé le ${profile.froid_valide_le}`
              : 'pas encore confirmé'}
          </b>
        </p>

        <div className="divider" />

        {/* --- Onboarding -------------------------------------------------- */}
        <h4 style={{ marginBottom: 6 }}>Questionnaire initial</h4>
        {onboarding?.done_at ? (
          <p className="tiny">
            Rempli le <b>{String(onboarding.done_at).slice(0, 10)}</b>
            {Array.isArray(profile.difficultes) && profile.difficultes.length > 0
              ? ` · difficultés déclarées : ${(profile.difficultes as string[]).join(', ')}`
              : ''}
          </p>
        ) : (
          <p className="tiny dim">
            Pas encore rempli. Il servira à adapter le programme — notamment à avancer
            les exercices sur les sensations si la panique est ta difficulté principale.
          </p>
        )}

        <div className="divider" />

        {/* --- Consentements ----------------------------------------------- */}
        <h4 style={{ marginBottom: 6 }}>Consentements</h4>
        <p className="tiny dim">
          Deux choses distinctes, et la seconde est refusable sans rien perdre.
        </p>
        <p className="tiny">
          <b>Traitement de tes données de santé</b> — nécessaire au fonctionnement :
          sans lui il n'y a ni suivi, ni analyse, ni mémoire. C'est l'objet même de
          l'application.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={consents.cohorte === true}
            disabled={saving}
            onChange={(event) => void setCohortConsent(event.target.checked)}
          />
          <span>
            <b>Contribuer aux statistiques collectives.</b> Tes données rejoignent une
            table de faits sans ton nom ni ton adresse, avec une tranche d'âge et un
            pays — jamais une ville. Rien de collectif ne te sera montré avant qu'il y
            ait au moins onze personnes dans une comparaison : en dessous, le chiffre
            serait à la fois faux et ré-identifiant. Refuser ne change rien au reste.
          </span>
        </label>

        <div className="divider" />

        {/* --- Le reste : réglages existants, non dupliqués ---------------- */}
        <Account />

        <div className="divider" />

        <h4 style={{ marginBottom: 6 }}>Session</h4>
        <div className="btn-row">
          <button className="btn-sm" onClick={logout}>
            Se déconnecter
          </button>
        </div>

        {note && <p className="tiny">{note}</p>}
      </div>
    </div>
  )
}
