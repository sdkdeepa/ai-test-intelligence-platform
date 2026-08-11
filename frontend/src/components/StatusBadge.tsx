import './StatusBadge.css'

// One badge component for every closed-vocabulary status field in the
// platform (analysis state, release recommendation, failure classification,
// suggestion review status) rather than one component per field — the
// values don't overlap, so a single lookup table is simpler than four
// near-identical components.
const TONE_BY_VALUE: Record<string, 'neutral' | 'info' | 'positive' | 'caution' | 'negative'> = {
  // analysis run state
  pending: 'neutral',
  running: 'info',
  completed: 'positive',
  failed: 'negative',
  // release recommendation
  proceed: 'positive',
  caution: 'caution',
  block: 'negative',
  // failure classification
  regression: 'negative',
  flaky: 'caution',
  environment: 'caution',
  unknown: 'neutral',
  // suggestion review status
  accepted: 'positive',
  rejected: 'negative',
}

interface StatusBadgeProps {
  value: string
}

export function StatusBadge({ value }: StatusBadgeProps) {
  const tone = TONE_BY_VALUE[value] ?? 'neutral'
  return (
    <span className={`status-badge status-badge--${tone}`}>
      {value}
    </span>
  )
}
