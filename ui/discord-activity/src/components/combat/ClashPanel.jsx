import { Swords } from 'lucide-react'
import { Button } from '../ui/Button'

// Painel de Clash — a lógica real do clash fica com o backend/bot;
// aqui só existe a interface de seleção e disparo da ação.
export function ClashPanel({ skills, selectedTargetName }) {
  return (
    <section className="combat-panel">
      <header><Swords /><h3>Clash</h3></header>
      <p className="section-hint">
        {selectedTargetName ? <>Alvo selecionado: <strong>{selectedTargetName}</strong></> : 'Nenhum alvo selecionado.'}
      </p>
      <div className="skill-pick-list">
        {skills.map(skill => (
          <button key={skill.id} className="skill-pick">
            <span>{skill.slot}</span>
            <strong>{skill.name}</strong>
            <small>{skill.basePower} Base · {skill.coinPower} Coin</small>
          </button>
        ))}
      </div>
      <Button variant="solid" icon={Swords} disabled={!selectedTargetName}>Iniciar Clash</Button>
    </section>
  )
}
