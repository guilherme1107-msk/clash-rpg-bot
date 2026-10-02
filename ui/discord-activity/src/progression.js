export const UPTIE_COSTS = [0, 40, 80, 150, 300]
export const UPTIE_UNLOCKS = [
  ['Kit básico e passivas iniciais'],
  ['Refinamento de skills e passiva de Sanidade Alta'],
  ['Skill 3, melhoria média e Velocidade'],
  ['Melhoria grande e passiva de suporte'],
  ['Melhoria colossal, Singularidade e novos E.G.O.'],
]

export const abilityModifier = value => Math.max(-5, Math.min(10, Math.floor((Number(value || 10) - 10) / 2)))

export function levelValues({ level = 1, strength = 10, constitution = 10, hpRollTotal = 54 }) {
  const safeLevel = Math.max(1, Number(level))
  const strengthMod = abilityModifier(strength)
  const constitutionMod = abilityModifier(constitution)
  const maxHp = Math.max(1, Number(hpRollTotal) + 50 + 10 * Math.max(0, constitutionMod) + (safeLevel - 1) * (5 + constitutionMod))
  const maxLight = 3 + Math.floor(safeLevel / 4) + (safeLevel >= 30 ? 7 : safeLevel >= 20 ? 5 : 0)
  return { level: safeLevel, offense: safeLevel * (3 + Math.floor(strengthMod / 2)), defense: safeLevel * (3 + Math.floor(constitutionMod / 2)), maxHp, maxStagger: Math.floor(maxHp / 2), maxLight, trainedGrade: safeLevel + 3, untrainedGrade: Math.floor(safeLevel / 2), proficiencySlots: Math.floor(safeLevel / 3) }
}

export const PROFICIENCY_CATALOG = [
  ['Luta','strength','X'],['Atletismo','strength',''],['Acrobacia','dexterity',''],['Furtividade','dexterity',''],['Iniciativa','dexterity',''],['Crime','dexterity','XY'],['Pilotagem','dexterity','X'],['Pontaria','dexterity','X'],['Reflexos','dexterity',''],['Fortitude','constitution',''],['Atualidades','intelligence',''],['Tecnologia','intelligence','XY'],['Investigação','intelligence',''],['Profissão','intelligence','X'],['Medicina','intelligence','Y'],['Ciências','intelligence','X'],['Tática','intelligence','X'],['Intuição','wisdom',''],['Percepção','wisdom',''],['Vontade','wisdom',''],['Sobrevivência','wisdom',''],['Adestramento','charisma','X'],['Artes','charisma','X'],['Diplomacia','charisma',''],['Enganação','charisma',''],['Intimidação','charisma',''],
].map(([name, attribute, requirement]) => ({ name, attribute, requirement }))

export function computedProficiencies(attributes = {}, selected = [], level = 1) {
  const trained = new Set((selected || []).map(item => typeof item === 'string' ? item : item.name))
  const values = levelValues({ level })
  return PROFICIENCY_CATALOG.map(item => {
    const isTrained = trained.has(item.name)
    const modifier = abilityModifier(attributes[item.attribute])
    return {...item, trained: isTrained, grade: isTrained ? values.trainedGrade : values.untrainedGrade, value: modifier + (isTrained ? values.trainedGrade : values.untrainedGrade)}
  })
}
