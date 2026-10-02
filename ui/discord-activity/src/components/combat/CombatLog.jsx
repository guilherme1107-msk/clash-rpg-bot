// Histórico em estilo "log de terminal" — reaproveitado na aba de
// Histórico da ficha e na tela de combate.
export function CombatLog({ entries }) {
  return (
    <div className="combat-log">
      {entries.map(entry => (
        <div key={entry.id} className={`log-line kind-${entry.kind}`}>
          <span className="log-time">[{entry.timestamp}]</span>
          <span className="log-turn">T{entry.turn}</span>
          <span className="log-text">{entry.text}</span>
        </div>
      ))}
    </div>
  )
}
