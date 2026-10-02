import { useRef, useState } from 'react'
import { Crosshair } from 'lucide-react'

// Seleção de alvo por "arrastar" o reticle do seu personagem até o alvo
// desejado no campo de batalha — funciona com mouse e toque (pointer events).
export function TargetSelector({ targets, selectedTargetId, onSelect }) {
  const fieldRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [reticlePos, setReticlePos] = useState(null)

  const handlePointerDown = e => {
    setDragging(true)
    updatePosition(e)
    e.target.setPointerCapture?.(e.pointerId)
  }

  const handlePointerMove = e => {
    if (!dragging) return
    updatePosition(e)
  }

  const updatePosition = e => {
    const field = fieldRef.current
    if (!field) return
    const rect = field.getBoundingClientRect()
    setReticlePos({
      x: Math.max(0, Math.min(rect.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, e.clientY - rect.top)),
    })
  }

  const handlePointerUp = e => {
    if (!dragging) return
    setDragging(false)
    const el = document.elementFromPoint(e.clientX, e.clientY)
    const targetEl = el?.closest('[data-target-id]')
    if (targetEl) onSelect(targetEl.dataset.targetId)
    setReticlePos(null)
  }

  return (
    <div className="target-selector">
      <p className="section-hint">Arraste o reticle até o alvo para selecioná-lo.</p>
      <div className="battlefield" ref={fieldRef} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}>
        {targets.map(target => (
          <button
            key={target.id}
            data-target-id={target.id}
            className={`target-token kind-${target.kind} ${selectedTargetId === target.id ? 'selected' : ''}`}
            onClick={() => onSelect(target.id)}
          >
            <span className="target-name">{target.name}</span>
            <span className="target-hp">{target.hp.current}/{target.hp.maximum} HP</span>
          </button>
        ))}

        <div
          className="drag-reticle"
          onPointerDown={handlePointerDown}
          style={reticlePos ? { left: reticlePos.x, top: reticlePos.y, position: 'absolute' } : undefined}
        >
          <Crosshair />
        </div>
      </div>
    </div>
  )
}
