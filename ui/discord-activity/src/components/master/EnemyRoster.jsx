import { CombatMeter } from '../ui/CombatMeter'
import { ResourceMeter } from '../ui/ResourceMeter'

// Lista de inimigos com seus recursos, editável só pelo mestre.
export function EnemyRoster({ enemies }) {
  return (
    <div className="enemy-roster">
      {enemies.map(enemy => (
        <article key={enemy.id} className="enemy-card">
          <header>
            <img src={enemy.portrait} alt="" className="enemy-portrait" />
            <div>
              <h3>{enemy.name}</h3>
              <span>Iniciativa {enemy.initiative}</span>
            </div>
          </header>
          <CombatMeter label="HP" tone="hp" current={enemy.hp.current} maximum={enemy.hp.maximum} />
          <CombatMeter label="STAGGER" tone="stagger" current={enemy.stagger.current} maximum={enemy.stagger.maximum} />
          <div className="enemy-stats-row">
            <span>OFFENSE <strong>{enemy.offense}</strong></span>
            <span>DEFENSE <strong>{enemy.defense}</strong></span>
          </div>
          {enemy.statuses.length > 0 && (
            <div className="enemy-statuses">
              {enemy.statuses.map(status => (
                <ResourceMeter key={status.id} label={status.name} current={status.potency} detail={`Count ${status.count}`} />
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  )
}
