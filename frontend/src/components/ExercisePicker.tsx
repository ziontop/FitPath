import { useEffect, useState } from 'react'
import { SearchX } from 'lucide-react'
import { exercises as exercisesApi } from '../api'
import type { Exercise } from '../api'
import { Modal, Input, List, ListRow, Badge, Skeleton, EmptyState } from './ui'
import { humanize } from '../lib/format'

interface Props {
  open: boolean
  onClose: () => void
  onPick: (exercise: Exercise) => void
}

/** Searchable exercise catalog picker (debounced against /api/exercises). */
export function ExercisePicker({ open, onClose, onPick }: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Exercise[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    const id = window.setTimeout(() => {
      exercisesApi
        .list({ q: q || undefined, limit: 30 })
        .then((r) => alive && setResults(r.items))
        .catch(() => alive && setResults([]))
        .finally(() => alive && setLoading(false))
    }, 220)
    return () => {
      alive = false
      window.clearTimeout(id)
    }
  }, [q, open])

  return (
    <Modal open={open} onClose={onClose} title="Add exercise">
      <Input
        placeholder="Search exercises…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoFocus
        aria-label="Search exercises"
      />
      <div className="exercise-pick" style={{ marginTop: 12 }}>
        {loading ? (
          <div className="exercise-pick__loading">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="exercise-pick__skeleton-row">
                <Skeleton variant="text" width="55%" />
                <Skeleton variant="text" width="35%" style={{ marginTop: 6 }} />
              </div>
            ))}
          </div>
        ) : results.length === 0 ? (
          <EmptyState
            icon={<SearchX size={28} aria-hidden="true" />}
            title="No exercises found"
            text="Try a different search term or muscle group."
          />
        ) : (
          <List>
            {results.map((ex) => (
              <ListRow
                key={ex.id}
                role="button"
                tabIndex={0}
                onClick={() => {
                  onPick(ex)
                  onClose()
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    onPick(ex)
                    onClose()
                  }
                }}
                title={ex.name}
                sub={`${humanize(ex.primary_muscle)} · ${humanize(ex.equipment)}`}
                trailing={ex.is_main_lift ? <Badge variant="primary">Main lift</Badge> : null}
              />
            ))}
          </List>
        )}
      </div>
    </Modal>
  )
}
