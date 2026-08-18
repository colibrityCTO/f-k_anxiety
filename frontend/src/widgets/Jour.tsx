import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { ProgramDay, WidgetType } from '../lib/types'

/**
 * Le parcours du jour.
 *
 * `build_day()` calcule cinq à huit items chaque jour, chacun avec sa justification
 * chiffrée. L'ouverture du fil n'en propose **qu'un** — c'est volontaire, une liste de
 * huit choses à faire se referme sans rien faire. Mais il fallait un endroit pour voir
 * le reste, sans quoi le travail du moteur adaptatif restait invisible.
 *
 * D'où la hiérarchie affichée : le **socle** est ce qui tient le suivi, le **module**
 * est la semaine en cours, l'**adaptatif** est ce que tes propres données ont
 * déclenché. Un seul item est présenté comme attendu — le check-in. Le reste est
 * optionnel, et c'est écrit : le programme n'est pas une liste de courses, et
 * `ROADMAP.md` écarte explicitement toute forme de série à préserver.
 */

const SLOTS: { key: string; title: string; note: string }[] = [
  {
    key: 'socle',
    title: 'Le socle',
    note: 'Tous les jours. Sans mesure quotidienne, rien du reste n’est interprétable.',
  },
  {
    key: 'module',
    title: 'Cette semaine',
    note: 'La progression du programme, sur douze semaines.',
  },
  {
    key: 'adaptatif',
    title: 'Déclenché par tes données',
    note: 'Proposé à cause de ce que tes chiffres montrent — chaque item dit lequel.',
  },
]

export default function Jour({ busy, onOpen }: WidgetProps) {
  const [day, setDay] = useState<ProgramDay | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState<string | null>(null)

  useEffect(() => {
    api
      .programDay()
      .then(setDay)
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : 'Programme indisponible.'),
      )
  }, [])

  if (error) return <div className="w-body"><p className="error-text">{error}</p></div>
  if (!day) return <div className="w-body"><p className="dim">Chargement…</p></div>

  const done = day.items.filter((i) => i.status === 'fait' || i.status === 'partiel').length

  return (
    <div className="w-body">
      <p className="tiny dim">
        Semaine {day.week} · module {day.module} — {day.module_title}. {day.module_goal}
      </p>
      <div className="sum">
        <div>
          <span>Fait aujourd'hui</span>
          <b>
            {done}/{day.items.length}
          </b>
        </div>
        <div>
          <span>Jours d'affilée</span>
          <b>{day.streak}</b>
        </div>
        <div>
          <span>Assiduité 7 j</span>
          <b>{Math.round(day.adherence_7j * 100)} %</b>
        </div>
      </div>

      {day.notices.map((notice) => (
        <p className="frame-note" key={notice}>
          {notice}
        </p>
      ))}

      {SLOTS.map((slot) => {
        const items = day.items.filter((item) => item.slot === slot.key)
        if (items.length === 0) return null
        return (
          <div key={slot.key}>
            <h4 className="sec">{slot.title}</h4>
            <p className="tiny dim">{slot.note}</p>
            {items.map((item, index) => {
              const finished = item.status === 'fait' || item.status === 'partiel'
              const open = shown === item.activity.slug
              /* `build_day` donne **une** justification par module, pas par activité :
                 les trois items de la semaine portent donc le même texte. L'afficher
                 trois fois ressemblait à un bug d'affichage. On ne le montre qu'une
                 fois par bloc, sauf s'il diffère réellement — ce qui est le cas des
                 items adaptatifs, dont chacun a la sienne. */
              const repeated = index > 0 && items[index - 1].why_for_you === item.why_for_you
              return (
                <div className={`plan${finished ? ' plan-done' : ''}`} key={item.activity.slug}>
                  <div className="plan-head">
                    <b>{item.activity.title}</b>
                    <span className="tiny dim">
                      {item.activity.duration_min} min · niveau {item.activity.evidence_level}
                      {finished ? ' · fait' : item.status === 'reporte' ? ' · reporté' : ''}
                    </span>
                  </div>
                  {/* La justification est celle calculée par le serveur, avec les
                      chiffres de la personne. On ne la reformule pas : elle est déjà
                      personnalisée, et la réécrire ajouterait un risque d'invention. */}
                  {!repeated && (
                    <p className="tiny">
                      {open || item.why_for_you.length <= 140
                        ? item.why_for_you
                        : `${item.why_for_you.slice(0, 130)}…`}{' '}
                      {(item.why_for_you.length > 140 || item.triggered_by.length > 0) && (
                        <button
                          className="linkish"
                          onClick={() => setShown(open ? null : item.activity.slug)}
                        >
                          {open ? 'réduire' : 'pourquoi'}
                        </button>
                      )}
                    </p>
                  )}
                  {/* Le mécanisme de l'activité elle-même : c'est ce qui distingue deux
                      items d'un même module, là où la justification les confond. */}
                  <p className="tiny dim">{item.activity.mechanism.slice(0, 150)}…</p>
                  {open && item.triggered_by.length > 0 && (
                    <ul className="source-list">
                      {item.triggered_by.map((trigger, index) => (
                        <li key={index}>
                          <b>{String(trigger.libelle ?? '')}</b> : {String(trigger.valeur ?? '')}
                          {trigger.methode ? ` — ${String(trigger.methode)}` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="btn-row">
                    {item.widget ? (
                      <button
                        className="btn-sm"
                        disabled={busy}
                        onClick={() => onOpen?.(item.widget as WidgetType, item.activity.title)}
                      >
                        {finished ? 'Le refaire' : 'Ouvrir'}
                      </button>
                    ) : (
                      /* `widget: null` n'est pas un oubli : sommeil, activité physique et
                         caféine sont des habitudes à changer, pas des exercices à
                         minuter. Ouvrir un formulaire n'y servirait à rien. */
                      <span className="tiny dim">
                        Rien à ouvrir : c'est une habitude à changer, pas un exercice.
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}

      <WhyBox
        mechanism="Le programme suit le Protocole Unifié : un tronc commun de douze semaines, validé par essai d'équivalence contre les protocoles spécifiques au trouble panique, à l'anxiété généralisée et à l'anxiété sociale. Les particularités ne sont pas traitées par un parcours séparé mais par la couche adaptative, qui ajoute des activités en fonction de ce que tes données montrent — et une association qui n'a pas survécu à la correction statistique ne déclenche rien."
        evidenceLevel="A"
        sources={[
          {
            label:
              'Barlow et al., World Psychiatry 2020 — Protocole Unifié ; essai d’équivalence, JAMA Psychiatry 2017',
            url: 'https://onlinelibrary.wiley.com/doi/10.1002/wps.20748',
          },
          {
            label: 'NICE CG113 — interventions de faible intensité en première étape',
            url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
          },
        ]}
        data={[
          { label: 'Progression', value: `semaine ${day.week} sur 12` },
          { label: 'Un seul item attendu', value: 'le check-in — le reste est optionnel' },
        ]}
        contraindications="Ce n'est pas une liste à cocher, et il n'y a pas de série à préserver. Trois minutes tenues valent mieux qu'une heure prévue et non faite : une activité non faite est une donnée sur le format, pas un échec."
      />
    </div>
  )
}
