import Icon from './Icon'

/**
 * Le bouton du compte, en haut à droite de la barre.
 *
 * Une icône et pas un libellé : la barre est étroite sur téléphone, et le nom de
 * l'application y tient déjà.
 *
 * Le point d'attention n'est pas décoratif. Il signale ce que l'utilisateur ne peut
 * pas deviner autrement : un consentement jamais répondu, un questionnaire initial
 * jamais rempli. Sans lui, ces éléments resteraient dans une page qu'on n'ouvre que
 * pour se déconnecter — donc jamais.
 */
export default function AccountLink({
  attention,
  onOpen,
}: {
  attention: string | null
  onOpen: () => void
}) {
  return (
    <button
      className={`iconbtn topbtn${attention ? ' has-dot' : ''}`}
      aria-label={attention ? `Compte — ${attention}` : 'Compte'}
      title={attention ?? 'Compte'}
      onClick={onOpen}
    >
      <Icon name="account" />
    </button>
  )
}
