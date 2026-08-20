/**
 * La progression d'un formulaire en plusieurs étapes.
 *
 * Deux exigences, et la seconde explique la forme retenue. **Une seule étape à
 * l'écran** : un formulaire qui déroule sept champs, deux curseurs et un minuteur
 * d'un coup se lit comme une corvée, et sous anxiété une page longue est en
 * elle-même un motif d'abandon. Et **toutes les étapes visibles** malgré tout :
 * savoir combien il en reste est ce qui permet de commencer. « Encore trois
 * questions » se supporte, « je ne sais pas où ça s'arrête » non.
 *
 * D'où des segments plutôt qu'une barre continue. Une barre remplie à 40 % dit la
 * proportion mais pas le nombre ; six segments disent les deux d'un coup. Le
 * segment courant porte un trait épais, les faits sont pleins, les suivants en
 * filet — la même grammaire que les cases du socle en haut de l'écran, pour que
 * « rempli = fait » veuille dire la même chose partout dans l'application.
 *
 * Cliquable vers l'arrière seulement : revenir sur ce qu'on a répondu est
 * légitime, sauter en avant contournerait des champs dont la suite dépend — la
 * prédiction s'écrit *avant* l'exercice, et c'est tout l'objet de l'exercice.
 */
export default function Steps({
  index,
  titles,
  onGo,
}: {
  /** Index de l'étape courante, à partir de 0. */
  index: number
  /** Le titre de chaque étape. Sa longueur donne le nombre de segments. */
  titles: string[]
  /** Retour en arrière. Absent : la progression est alors purement indicative. */
  onGo?: (index: number) => void
}) {
  return (
    <div className="steps">
      <div className="steps-bar">
        {titles.map((title, i) => {
          const done = i < index
          const current = i === index
          const reachable = Boolean(onGo) && i < index
          return (
            <button
              key={title}
              type="button"
              className={`steps-seg${done ? ' is-done' : ''}${current ? ' is-current' : ''}`}
              disabled={!reachable}
              aria-current={current ? 'step' : undefined}
              aria-label={`Étape ${i + 1} sur ${titles.length} — ${title}`}
              title={title}
              onClick={() => reachable && onGo?.(i)}
            />
          )
        })}
      </div>
      <p className="steps-label">
        Étape {index + 1} sur {titles.length} — {titles[index]}
      </p>
    </div>
  )
}
