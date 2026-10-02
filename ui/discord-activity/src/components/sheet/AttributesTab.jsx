import { abilityModifier, computedProficiencies } from '../../progression'

const RESISTANCE_TIER_LABEL = {
  fraco: 'Fraco',
  normal: 'Normal',
  resistente: 'Resistente',
  imune: 'Imune',
}

// Atributos e perícias em lista simples (nome + valor);
// resistências com ícone + tier (fraco/normal/resistente/imune).
export function AttributesTab({ character }) {
  const attributeKeys = { Strength: 'STR', Dexterity: 'DEX', Constitution: 'CON', Intelligence: 'INT', Wisdom: 'SAB', Charisma: 'CAR' }
  const attributes = Object.fromEntries((character.attributes || []).map(item => [String(item.name).toLowerCase(), Number(item.value || 10)]))
  const proficiencies = computedProficiencies(attributes, character.proficiencies, character.level)
  return (
    <div className="attributes-tab">
      <section className="attribute-dossier">
        <header><span>⊱ ATRIBUTOS ⊰</span><small>Nível {character.level || 1} · bônus calculados automaticamente</small></header>
        <ul>
          {character.attributes.map(attr => {
            const mod = abilityModifier(attr.value)
            return <li key={attr.name}><b>[{attributeKeys[attr.name] || attr.name.slice(0, 3).toUpperCase()}]</b><span>{attr.name}</span><strong>{attr.value}</strong><em>({mod >= 0 ? '+' : ''}{mod})</em></li>
          })}
        </ul>
      </section>
      <section className="proficiency-dossier">
        <header><div><span>⊱ PERÍCIAS ⊰</span><p>Treinada: +{character.level + 3} · Não treinada: +{Math.floor(character.level / 2)}</p></div><small>-X requer treino · -Y requer kit · -XY requer ambos</small></header>
        <ul>
          {proficiencies.map(prof => <li key={prof.name} className={prof.trained ? 'trained' : ''}>
            <i>{prof.trained ? '◆' : '◇'}</i><span>{prof.name}{prof.requirement ? `-${prof.requirement}` : ''}</span><b>[ {attributeKeys[prof.attribute[0].toUpperCase() + prof.attribute.slice(1)] || prof.attribute.slice(0, 3).toUpperCase()} ]</b><strong>{prof.value >= 0 ? '+' : ''}{String(prof.value).padStart(2, '0')}</strong>
          </li>)}
        </ul>
      </section>
      <section>
        <h3>Resistências</h3>
        <ul className="resistance-list">
          {character.resistances.map(res => (
            <li key={res.name} className={`tier-${res.tier}`}>
              <span className="res-name">{res.name}</span>
              <span className="res-tier">{RESISTANCE_TIER_LABEL[res.tier]}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
