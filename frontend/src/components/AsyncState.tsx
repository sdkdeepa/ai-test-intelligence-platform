import './AsyncState.css'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return <p className="async-state async-state--loading">{label}</p>
}

export function ErrorState({ message }: { message: string }) {
  return (
    <p className="async-state async-state--error" role="alert">
      {message}
    </p>
  )
}

export function EmptyState({ message }: { message: string }) {
  return <p className="async-state async-state--empty">{message}</p>
}
