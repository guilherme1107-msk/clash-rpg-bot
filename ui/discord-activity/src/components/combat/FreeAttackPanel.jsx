import { Zap } from 'lucide-react'
import { Button } from '../ui/Button'

// Ataque livre — ação simplificada, sem gastar uma skill específica.
export function FreeAttackPanel({ selectedTargetName }) {
  return (
    <section className="combat-panel">
      <header><Zap /><h3>Ataque Livre</h3></header>
      <p className="section-hint">
        {selectedTargetName ? <>Alvo selecionado: <strong>{selectedTargetName}</strong></> : 'Nenhum alvo selecionado.'}
      </p>
      <Button variant="ghost" icon={Zap} disabled={!selectedTargetName}>Atacar livremente</Button>
    </section>
  )
}
