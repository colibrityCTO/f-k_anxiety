/**
 * Icônes maison : géométrie à angles droits, trait épais, aucun coin arrondi et
 * aucune courbe organique. Dessinées ici plutôt qu'importées d'un jeu « friendly ».
 */
const PATHS: Record<string, string> = {
  plus: 'M10 2v16M2 10h16',
  minus: 'M2 10h16',
  close: 'M3 3l14 14M17 3L3 17',
  checkin: 'M3 3h14v14H3zM6 10l3 3 5-6',
  breath: 'M3 3h14v14H3zM7 10h6',
  journal: 'M4 2h12v16H4zM7 6h6M7 10h6M7 14h3',
  scale: 'M3 16h14M5 16V9M9 16V5M13 16v-4M17 16v-8',
  stats: 'M2 14l4-5 4 3 3-6 5 4M2 17h16',
  analysis: 'M3 3h14v14H3zM6 13l3-4 2 2 3-5',
  sources: 'M3 4h6v12H3zM11 4h6v12h-6z',
  expo: 'M10 2v12M5 9l5 5 5-5M3 17h14',
  meditation: 'M3 3h14v14H3zM7 7h6v6H7z',
  memory: 'M3 4h14v4H3zM3 12h14v4H3zM6 6h2M6 14h2',
  sensations: 'M2 10h3l2-5 3 10 3-7 2 2h3',
  report: 'M4 2h12v16H4zM7 6h6M7 9h6M7 12h4M7 15h2',
  account: 'M4 3h12v14H4zM7 8h6M7 12h4',
  logout: 'M8 3H3v14h5M12 6l4 4-4 4M8 10h8',
}

export default function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const path = PATHS[name] ?? PATHS.plus
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      stroke="currentColor"
      strokeWidth={2.5}
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  )
}
