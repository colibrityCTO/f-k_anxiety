export default function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 10,
  lowLabel = 'aucune',
  highLabel = 'maximale',
  suffix = '',
  note,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  lowLabel?: string
  highLabel?: string
  suffix?: string
  /** Mention « déduit de ta phrase », affichée quand la valeur vient d'une extraction. */
  note?: string
}) {
  return (
    <div className="slider">
      <div className="head">
        <label htmlFor={`s-${label}`} style={{ marginBottom: 0 }}>
          {label}
        </label>
        <span className="val">
          {value}
          {suffix}
        </span>
      </div>
      <input
        id={`s-${label}`}
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="scale">
        <span>
          {min} {lowLabel}
        </span>
        <span>
          {max} {highLabel}
        </span>
      </div>
      {note && <p className="tiny dim" style={{ marginTop: 4, marginBottom: 0 }}>{note}</p>}
    </div>
  )
}
