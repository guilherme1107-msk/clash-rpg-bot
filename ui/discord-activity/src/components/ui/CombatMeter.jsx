// Medidor "dramático" reservado aos números de combate principais:
// HP, SP, Stagger, Light. Visualmente mais forte que o ResourceMeter.
// tone: 'hp' | 'sp' | 'stagger' | 'light'
export function CombatMeter({ label, current, maximum, tone = 'hp' }) {
  const pct = maximum > 0 ? Math.max(0, Math.min(100, (current / maximum) * 100)) : 0
  return (
    <div className={`combat-meter tone-${tone}`}>
      <div className="combat-meter-head">
        <span>{label}</span>
        <strong>{current}<i>/</i>{maximum}</strong>
      </div>
      <div className="combat-meter-track">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
