import type { ReactNode } from 'react'

import './Card.css'

interface CardProps {
  title?: string
  children: ReactNode
}

export function Card({ title, children }: CardProps) {
  return (
    <section className="card">
      {title && <h3 className="card__title">{title}</h3>}
      {children}
    </section>
  )
}
