import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

/**
 * Le récapitulatif d'un épisode, déposé dans le fil **après** la crise.
 *
 * En lecture seule, et il n'y a rien à valider : l'épisode est déjà enregistré au
 * moment où ce bloc apparaît. Sa raison d'être est l'accumulation — c'est la
 * finalité que le programme donne à ce log : au bout de quelques semaines, ces
 * lignes deviennent la preuve que l'anxiété passe toujours et que la catastrophe
 * annoncée n'a pas eu lieu.
 */
export default function Panique({ item }: WidgetProps) {
  const saved = item.saved_values ?? {}
  const cells = [
    ['Pic', saved.pic],
    ['Après', saved.apres],
    ['Durée', saved.minutes === null || saved.minutes === undefined ? null : `${saved.minutes} min`],
    ['Outils', saved.outils],
    [
      'Ce que tu redoutais',
      saved.redoute_arrive === null || saved.redoute_arrive === undefined
        ? null
        : saved.redoute_arrive
          ? 'est arrivé'
          : "n'est pas arrivé",
    ],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '')

  return (
    <div className="w-body">
      <div className="sum">
        {cells.map(([label, value]) => (
          <div key={String(label)}>
            <span>{String(label)}</span>
            <b>{String(value)}</b>
          </div>
        ))}
      </div>

      {typeof saved.bilan === 'string' && saved.bilan && (
        <p className="qc-proof" style={{ marginTop: 'var(--g2)' }}>
          {saved.bilan.replace(/\*\*/g, '')}
        </p>
      )}

      <WhyBox
        mechanism="Ce log a une fonction précise : accumuler. Une crise, prise seule, ne prouve rien — dix crises notées avec leur durée et ce qui s'est réellement passé constituent la seule preuve qui compte contre la prédiction catastrophique, parce qu'elle est faite de tes propres données. La question « ce que tu redoutais, c'est arrivé ? » est posée à toi et non déduite : l'application ne peut pas juger d'un texte libre, et prétendre le faire serait une invention."
        evidenceLevel="B"
        sources={[
          {
            label:
              'Craske et al., Behav Res Ther 2014 — violation d’attente : ce qui produit l’apprentissage, c’est l’écart entre la prédiction et le résultat',
            url: 'https://pubmed.ncbi.nlm.nih.gov/24864005/',
          },
        ]}
        contraindications="Si tu ouvres le mode crise très souvent et que ton GAD-7 ne bouge pas, l'application te le dira : à ce stade, l'écran est probablement devenu ce qui te rassure plutôt que ce qui te fait apprendre."
      />
    </div>
  )
}
