import { useEffect, useState } from 'react'
import { Minus, Plus, Pause, Play } from 'lucide-react'
import { Button, IconButton } from './ui'
import { mmss } from '../lib/format'

interface Props {
  duration: number
  onClose: () => void
}

/** Prominent countdown rest timer with −30s / pause / +30s / skip controls. */
export function RestTimer({ duration, onClose }: Props) {
  const [remaining, setRemaining] = useState(duration)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (paused) return
    if (remaining <= 0) return
    const id = window.setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000)
    return () => window.clearInterval(id)
  }, [paused, remaining])

  const done = remaining <= 0

  return (
    <div className={`rest-timer${done ? ' is-done' : ''}`} role="timer" aria-live="polite">
      <span className="rest-timer__label">{done ? 'Rest complete' : 'Rest timer'}</span>
      <div className="rest-timer__main">
        {!done && (
          <IconButton
            label="Subtract 30 seconds"
            variant="solid"
            size="lg"
            onClick={() => setRemaining((r) => Math.max(0, r - 30))}
          >
            <Minus size={20} />
          </IconButton>
        )}
        <span className="rest-timer__time">{done ? "Time's up!" : mmss(remaining)}</span>
        {!done && (
          <IconButton
            label="Add 30 seconds"
            variant="solid"
            size="lg"
            onClick={() => setRemaining((r) => r + 30)}
          >
            <Plus size={20} />
          </IconButton>
        )}
      </div>
      <div className="rest-timer__controls">
        {!done && (
          <Button
            variant="secondary"
            onClick={() => setPaused((p) => !p)}
            leftIcon={paused ? <Play size={16} /> : <Pause size={16} />}
          >
            {paused ? 'Resume' : 'Pause'}
          </Button>
        )}
        <Button variant={done ? 'primary' : 'ghost'} onClick={onClose}>
          {done ? 'Done' : 'Skip'}
        </Button>
      </div>
    </div>
  )
}
