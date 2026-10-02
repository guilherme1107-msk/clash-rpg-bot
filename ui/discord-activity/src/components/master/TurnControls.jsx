import { SkipForward } from 'lucide-react'
import { Button } from '../ui/Button'

// Controle de turno/rodada — a lógica de avançar turno de verdade vem do
// backend; aqui é só a interface de controle usada pelo mestre.
export function TurnControls({ battleState, participantNames }) {
  return (
    <section className="turn-controls">
      <div className="round-badge">
        <span>RODADA</span>
        <strong>{battleState.round}</strong>
      </div>
      <ol className="turn-order">
        {battleState.turnOrder.map(id => (
          <li key={id} className={id === battleState.currentTurnId ? 'current' : ''}>
            {participantNames[id] || id}
          </li>
        ))}
      </ol>
      <Button variant="solid" icon={SkipForward}>Próximo turno</Button>
    </section>
  )
}
