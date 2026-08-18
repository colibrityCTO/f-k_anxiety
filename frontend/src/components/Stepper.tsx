export default function Stepper({
  label,
  value,
  onChange,
  min = 0,
  max = 99,
  step = 1,
  suffix = '',
  note,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  suffix?: string
  note?: string
}) {
  const clamp = (next: number) => Math.max(min, Math.min(max, Number(next.toFixed(1))))
  return (
    <div>
      <label style={{ marginBottom: 6 }}>{label}</label>
      <div className="stepper">
        <button type="button" aria-label={`Diminuer ${label}`} onClick={() => onChange(clamp(value - step))}>
          −
        </button>
        <div className="n">
          {value}
          {suffix}
        </div>
        <button type="button" aria-label={`Augmenter ${label}`} onClick={() => onChange(clamp(value + step))}>
          +
        </button>
      </div>
      {note && <p className="tiny dim" style={{ marginTop: 4, marginBottom: 0 }}>{note}</p>}
    </div>
  )
}
