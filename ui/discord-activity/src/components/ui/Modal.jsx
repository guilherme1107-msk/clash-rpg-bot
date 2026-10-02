import { X } from 'lucide-react'
import { useEffect } from 'react'

// Modal grande cobrindo a tela — usado principalmente na edição da ficha.
export function Modal({ title, eyebrow, open, onClose, children, footer }) {
  useEffect(() => {
    if (!open) return
    const onKey = e => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="ui-modal-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="ui-modal">
        <header className="ui-modal-head">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <h2>{title}</h2>
          </div>
          <button className="ui-modal-close" onClick={onClose} aria-label="Fechar">
            <X />
          </button>
        </header>
        <div className="ui-modal-body">{children}</div>
        {footer && <footer className="ui-modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}
