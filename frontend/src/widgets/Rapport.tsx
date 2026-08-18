import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { ReportPayload } from '../lib/types'

const KEY_SIGNALS = [
  'tendance_anxiete',
  'gad7',
  'adherence',
  'correlation_sommeil_anxiete',
  'correlation_cafeine_anxiete',
  'expositions',
  'effet_mesure_activites',
  'attaques_panique',
  'evitement',
]

/**
 * Rapport destiné à un professionnel.
 *
 * L'impression sort en **noir sur blanc** : le design system autorise les deux
 * fonds, et sur papier l'inversion est la seule option lisible — imprimer un
 * fond noir gâche l'encre et rend les courbes illisibles. Le contenu, lui, est
 * strictement celui du fil : aucun chiffre n'est recalculé pour l'occasion.
 */
export default function Rapport(_props: WidgetProps) {
  const [days, setDays] = useState(90)
  const [data, setData] = useState<ReportPayload | null>(null)

  useEffect(() => {
    setData(null)
    api.report(days).then(setData).catch(() => undefined)
  }, [days])

  if (!data) {
    return (
      <div className="w-body">
        <p className="small dim">Préparation du rapport…</p>
      </div>
    )
  }

  const signals = data.signaux.filter((signal) => KEY_SIGNALS.includes(signal.id))
  const gad7 = data.echelles.filter((row) => row.instrument === 'gad7')

  return (
    <>
      <div className="w-body">
        <div className="chips" style={{ marginBottom: 'var(--g2)' }}>
          {[30, 90, 180].map((range) => (
            <button key={range} className="chip" aria-pressed={days === range} onClick={() => setDays(range)}>
              {range} jours
            </button>
          ))}
        </div>

        <p className="small">
          Période du <strong>{data.periode.debut}</strong> au <strong>{data.periode.fin}</strong> ·
          semaine {data.programme.week}, module {data.programme.module} · statut{' '}
          {data.programme.status}
        </p>

        <div className="divider" />

        <h4 style={{ marginBottom: 6 }}>Ce que le rapport contient</h4>
        <ul className="source-list">
          <li>{signals.length} signaux chiffrés, avec leur méthode de calcul et leur effectif</li>
          <li>{gad7.length} mesure(s) GAD-7 avec les seuils et la DMCI de 4 points</li>
          <li>{data.expositions.length} item(s) d'échelle d'expositions et leur avancement</li>
          <li>{data.apprentissages.length} apprentissage(s) notés après exposition</li>
          <li>{data.activites.length} activité(s) : faites, non faites, effet moyen mesuré</li>
          <li>Le cadre et les limites, en tête de document</li>
        </ul>

        <WhyBox
          label="Ce que ce rapport n'est pas"
          mechanism="Ce n'est pas un compte rendu clinique et ça ne remplace aucun examen. C'est un relevé de tes propres données, avec la méthode de calcul de chaque chiffre, destiné à faire gagner du temps à un professionnel — il verra en deux minutes ce qui a bougé, ce qui a été fait, et ce qui n'a pas été fait."
          evidenceLevel="A"
          sources={[
            {
              label: "NICE CG113 — en l'absence d'amélioration après une intervention de faible intensité, l'étape suivante est une TCC accompagnée",
              url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
            },
            {
              label: 'Toussaint et al., J Affect Disord 2020 — DMCI du GAD-7 ≈ 4 points',
              url: 'https://pubmed.ncbi.nlm.nih.gov/32090765/',
            },
          ]}
          contraindications="L'impression sort en noir sur blanc — c'est la seule version lisible sur papier."
        />
      </div>

      <div className="w-foot">
        <button className="btn-primary" onClick={() => printReport(data)}>
          Imprimer / enregistrer en PDF
        </button>
      </div>
    </>
  )
}

// --- Génération du document imprimable --------------------------------------

function escape(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function table(headers: string[], rows: (string | number | null | undefined)[][]): string {
  if (rows.length === 0) return '<p class="dim">Aucune donnée sur la période.</p>'
  return `<table>
    <thead><tr>${headers.map((h) => `<th>${escape(h)}</th>`).join('')}</tr></thead>
    <tbody>${rows
      .map((row) => `<tr>${row.map((cell) => `<td>${escape(cell ?? '—')}</td>`).join('')}</tr>`)
      .join('')}</tbody>
  </table>`
}

function printReport(data: ReportPayload) {
  const signals = data.signaux.filter((signal) => KEY_SIGNALS.includes(signal.id))
  const window_ = window.open('', '_blank', 'width=900,height=1200')
  if (!window_) return

  const html = `<!doctype html>
<html lang="fr"><head><meta charset="utf-8" />
<title>FUCK ANXIETY — rapport du ${escape(data.genere_le)}</title>
<style>
  /* Noir sur blanc : version papier. Aucun arrondi, filets nets, grille stricte. */
  * { box-sizing: border-box; border-radius: 0 !important; }
  body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #000;
         background: #fff; margin: 0; padding: 28px 32px; font-size: 11pt; line-height: 1.45; }
  h1 { font-size: 26pt; letter-spacing: -0.02em; text-transform: uppercase; margin: 0 0 2px;
       font-weight: 800; }
  h2 { font-size: 12pt; text-transform: uppercase; letter-spacing: 0.08em; margin: 22px 0 6px;
       border-bottom: 2px solid #000; padding-bottom: 3px; }
  p { margin: 0 0 8px; }
  .meta { font-size: 9pt; text-transform: uppercase; letter-spacing: 0.14em; }
  .frame { border: 2px solid #000; padding: 10px 12px; margin: 12px 0 4px; font-size: 9.5pt; }
  table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin: 4px 0 10px; }
  th, td { border: 1px solid #000; padding: 3px 6px; text-align: left; vertical-align: top; }
  th { font-size: 8pt; text-transform: uppercase; letter-spacing: 0.06em; }
  .dim { color: #555; }
  .foot { margin-top: 24px; border-top: 2px solid #000; padding-top: 8px; font-size: 8.5pt; }
  @media print { body { padding: 0; } h2 { break-after: avoid; } table { break-inside: auto; } }
</style></head><body>

<h1>Fuck Anxiety</h1>
<p class="meta">Rapport généré le ${escape(data.genere_le)} · période du ${escape(data.periode.debut)} au ${escape(data.periode.fin)} (${data.periode.jours} jours)</p>
<p class="meta">${escape(data.compte.email)}${data.compte.depuis ? ` · compte créé le ${escape(data.compte.depuis)}` : ''}</p>

<div class="frame"><strong>Cadre et limites.</strong> ${escape(data.cadre)}</div>

<h2>Programme</h2>
${table(
  ['Semaine', 'Module', 'Statut', 'Jours d’affilée', 'GAD-7 le plus récent'],
  [[
    data.programme.week,
    `${data.programme.module} — ${data.programme.module_title}`,
    data.programme.status,
    data.programme.streak,
    data.programme.gad7_last !== null
      ? `${data.programme.gad7_last} (${data.programme.gad7_last_on ?? ''})`
      : '—',
  ]],
)}

<h2>Signaux chiffrés</h2>
${table(
  ['Signal', 'Valeur', 'Écart', 'Lecture', 'n', 'Méthode'],
  signals.map((signal) => [
    signal.label,
    typeof signal.value === 'object' ? '(détail)' : String(signal.value ?? '—'),
    signal.delta ?? '—',
    signal.verdict ?? '—',
    signal.n ?? '—',
    signal.method ?? '—',
  ]),
)}

<h2>GAD-7</h2>
<p class="dim">Seuils : 5 / 10 / 15 (léger / modéré / sévère). Une variation de moins de 4 points est du bruit de mesure (DMCI, Toussaint et al. 2020).</p>
${table(['Date', 'Score / 21', 'Sévérité'], data.echelles.filter((r) => r.instrument === 'gad7').map((r) => [r.taken_on, r.total, r.severity]))}

<h2>Autres échelles</h2>
${table(['Instrument', 'Date', 'Score', 'Lecture'], data.echelles.filter((r) => r.instrument !== 'gad7').map((r) => [r.instrument.toUpperCase(), r.taken_on, r.total, r.severity]))}

<h2>Échelle d'expositions</h2>
${table(
  ['Item', 'Type', 'Anxiété anticipée', 'Tentatives', 'Dernière', 'Maîtrisé', 'Apprentissage'],
  data.expositions.map((r) => [
    r.label, r.kind, r.anticipated_anxiety, r.attempts, r.last_attempt_on,
    r.mastered ? 'oui' : 'non', r.best_learning,
  ]),
)}

<h2>Apprentissages après exposition</h2>
${table(
  ['Date', 'Situation', 'Prédiction', 'Prob.', 'Résultat réel', 'Appris'],
  data.apprentissages.map((r) => [
    r.entry_date, r.situation, r.prediction,
    r.prediction_probability !== null && r.prediction_probability !== undefined ? `${r.prediction_probability} %` : '—',
    r.actual_outcome, r.learning,
  ]),
)}

<h2>Activités</h2>
${table(
  ['Activité', 'Faites', 'Non faites', 'Effet moyen sur l’anxiété'],
  data.activites.map((r) => [r.title, r.faites, r.non_faites, r.effet_moyen ?? '—']),
)}

<h2>Suivi quotidien</h2>
${table(
  ['Date', 'Anxiété', 'Humeur', 'Sommeil (h)', 'Évitement', 'Paniques'],
  data.quotidien.map((r) => [r.entry_date, r.anxiete, r.humeur, r.sommeil_h, r.evitement, r.paniques]),
)}

<div class="foot">
  Auto-assistance structurée fondée sur le Protocole Unifié (Barlow, <em>World Psychiatry</em> 2020 ;
  essai d'équivalence <em>JAMA Psychiatry</em> 2017) et les recommandations NICE CG113. Les chiffres
  de ce rapport sont calculés par le serveur sur l'historique complet ; aucun n'est produit par un
  modèle de langage. Aucun diagnostic, aucun conseil médicamenteux.
</div>

<script>window.onload = function () { window.print(); };</script>
</body></html>`

  window_.document.write(html)
  window_.document.close()
}
