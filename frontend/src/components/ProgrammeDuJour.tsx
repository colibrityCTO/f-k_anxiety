import { useEffect, useState } from 'react'
import WhyBox from './WhyBox'
import { api } from '../lib/api'
import type { LaunchType, ProgramDay } from '../lib/types'

/**
 * Le parcours du jour : ce que `build_day()` a calculé, et pourquoi.
 *
 * Cinq à huit items chaque jour, chacun avec sa justification chiffrée. Le fil n'en
 * propose **qu'un** — c'est volontaire, une liste de huit choses à faire se referme
 * sans rien faire. Le reste vit ici, dans le panneau dépliable sous le titre, et non
 * plus dans un widget du fil : un programme n'est pas un événement, c'est l'état du
 * jour. Le chercher dans un menu puis le voir défiler avec le reste du fil le rendait
 * introuvable deux minutes après l'avoir ouvert.
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
    key: 'corps',
    title: 'Le soir, le corps',
    note:
      'Une pratique corporelle chaque soir, qui change avec les semaines : étirements, ' +
      'puis relaxation musculaire, puis yoga doux, puis yoga nidra. Les niveaux de preuve ' +
      'ne sont pas les mêmes, et chacun le dit.',
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

/**
 * Le chargement du programme, partagé.
 *
 * Deux endroits en ont besoin et doivent voir exactement la même chose : le bandeau
 * permanent, qui n'en affiche que les chiffres, et le corps dépliable, qui affiche
 * le reste. Deux appels séparés auraient pu renvoyer deux états du jour différents.
 */
export function useProgramDay(): { day: ProgramDay | null; error: string | null } {
  const [day, setDay] = useState<ProgramDay | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .programDay()
      .then(setDay)
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : 'Programme indisponible.'),
      )
  }, [])

  return { day, error }
}

/**
 * Les cinq chiffres du jour. Séparés du reste parce qu'ils ne se replient pas et ne
 * défilent pas : c'est la donnée qu'on garde sous les yeux, pas un détail à
 * consulter. Le reste — module, notices, liste des activités — est du texte, et le
 * texte peut défiler.
 */
export function ChiffresDuJour({ day }: { day: ProgramDay }) {
  const socle = day.items.filter((i) => i.slot === 'socle')
  const socleDone = socle.filter((i) => i.status === 'fait' || i.status === 'partiel').length
  const extra = day.items.filter(
    (i) => i.slot !== 'socle' && (i.status === 'fait' || i.status === 'partiel'),
  ).length

  return (
    <div className="sum parcours-sum">
      <div>
        <span>Le socle</span>
        <b>
          {socleDone}/{socle.length}
        </b>
      </div>
      <div>
        <span>En plus</span>
        <b>{extra}</b>
      </div>
      <div>
        <span>Jours d'affilée</span>
        <b>{day.streak}</b>
      </div>
      {/* Les deux chiffres côte à côte : la semaine avance au calendrier, la pratique
          non. L'écart entre les deux explique pourquoi un module peut paraître hors
          sujet — et le masquer aurait laissé la question sans réponse. */}
      <div>
        <span>Jours pratiqués</span>
        <b>{day.jours_pratiques}</b>
      </div>
      {/* Chiffre enfin honnête : le dénominateur contient désormais les activités
          proposées et non faites. Il valait 100 % en permanence, parce que seules
          les réussites étaient enregistrées. */}
      <div>
        <span>Assiduité 7 j</span>
        <b>{Math.round(day.adherence_7j * 100)} %</b>
      </div>
    </div>
  )
}

export default function ProgrammeDuJour({
  day,
  busy,
  onOpen,
}: {
  day: ProgramDay
  busy: boolean
  onOpen: (type: LaunchType, label?: string) => void
}) {
  const [shown, setShown] = useState<string | null>(null)

  return (
    <>
      <p className="tiny dim">
        Semaine {day.week} · module {day.module} — {day.module_title}. {day.module_goal}
      </p>

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
                        onClick={() => onOpen(item.widget as LaunchType, item.activity.title)}
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
          {
            label: 'Ce qui est attendu',
            value: 'le socle seul — le reste est proposé, jamais dû',
          },
        ]}
        contraindications="Ce n'est pas une liste à cocher, et il n'y a pas de série à préserver. Trois minutes tenues valent mieux qu'une heure prévue et non faite : une activité non faite est une donnée sur le format, pas un échec."
      />
    </>
  )
}
