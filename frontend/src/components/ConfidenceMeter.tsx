import './ConfidenceMeter.css'

interface ConfidenceMeterProps {
  /** A 0–1 value (confidence_score, risk_score, ...). */
  value: number
  label?: string
}

/** A static filled bar — no transition/animation, per the operational-UI requirement. */
export function ConfidenceMeter({ value, label }: ConfidenceMeterProps) {
  const clamped = Math.max(0, Math.min(1, value))
  const percent = Math.round(clamped * 100)

  return (
    <div className="confidence-meter" role="img" aria-label={`${label ?? 'value'}: ${percent}%`}>
      <div className="confidence-meter__track">
        <div className="confidence-meter__fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="confidence-meter__value">{percent}%</span>
    </div>
  )
}
