import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { IconButton } from './IconButton'

function useOverlayEffects(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.classList.add('no-scroll')
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.classList.remove('no-scroll')
    }
  }, [open, onClose])
}

export interface ModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  useOverlayEffects(open, onClose)
  if (!open) return null
  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : 'Dialog'}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {title ? (
          <div className="modal__head">
            <h2 className="modal__title">{title}</h2>
            <IconButton label="Close" size="sm" onClick={onClose}>
              <X size={18} />
            </IconButton>
          </div>
        ) : null}
        <div>{children}</div>
        {footer ? <div style={{ marginTop: 'var(--sp-5)' }}>{footer}</div> : null}
      </div>
    </div>,
    document.body,
  )
}

export interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
}

export function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  useOverlayEffects(open, onClose)
  if (!open) return null
  return createPortal(
    <div className="sheet-overlay" onMouseDown={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : 'Sheet'}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="sheet__handle" />
        {title ? <h3 className="sheet__title">{title}</h3> : null}
        {children}
      </div>
    </div>,
    document.body,
  )
}
