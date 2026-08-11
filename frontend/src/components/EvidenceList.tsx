import './EvidenceList.css'

interface EvidenceListProps {
  items: string[]
  emptyText?: string
}

/** Renders any string[] field (evidence, hypotheses, recommendations, ...) as a plain list. */
export function EvidenceList({ items, emptyText = 'None recorded.' }: EvidenceListProps) {
  if (items.length === 0) {
    return <p className="evidence-list__empty">{emptyText}</p>
  }
  return (
    <ul className="evidence-list">
      {items.map((item, index) => (
        // Evidence strings have no stable id and never reorder in place — index is fine here.
        // eslint-disable-next-line react/no-array-index-key
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}
