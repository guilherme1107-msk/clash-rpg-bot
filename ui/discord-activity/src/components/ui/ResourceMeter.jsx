// Medidor genérico reaproveitável para qualquer recurso/status que tenha
// um valor atual e um máximo (diferente do CombatMeter, reservado a
// HP/SP/Stagger/Light). Também serve para Potency quando fizer sentido.
export function ResourceMeter({ label, current, maximum, detail }) {
  const pct = maximum > 0 ? Math.max(0, Math.min(100, (current / maximum) * 100)) : 0
  return (
    <div className="resource-meter">
      <div className="resource-meter-head">
        <span>{label}</span>
        <strong>{current}{maximum != null && <><i>/</i>{maximum}</>}</strong>
      </div>
      {maximum != null && (
        <div className="resource-meter-track">
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      {detail && <small>{detail}</small>}
    </div>
  )
}
