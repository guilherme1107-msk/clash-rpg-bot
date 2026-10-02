import { createContext, useContext, useMemo } from 'react'
import { battleStateMock, combatLogMock, combatTargetsMock, enemiesMock, themesMock } from './mockData'

const ActivityDataContext = createContext(null)

const titleCase = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, item => item.toUpperCase())
const slotRank = value => { const slot=String(value||'').toLowerCase(),attack=slot.match(/^s([1-3])(?:-(\d+))?$/),defense=slot.match(/^d(\d+)(?:-(\d+))?$/);if(attack)return Number(attack[1])*100+(Number(attack[2])||0);if(defense)return 1000+Number(defense[1])*100+(Number(defense[2])||0);return 900 }
const slotLabel = (value,type) => { const slot=String(value||'').toLowerCase(); if(slot.startsWith('d'))return `Defensiva ${slot.slice(1)}`;if(slot.startsWith('s'))return slot.toUpperCase();return ['guard','evade','counter','clashable_guard','clashable_counter','assist_defense'].includes(type)?'Defensiva 1':'S1' }
const skillTypeLabel = value => ({attack:'Ataque',guard:'Guarda',evade:'Evasiva',counter:'Counter',clashable_guard:'Guarda Clashable',clashable_counter:'Counter Clashable',assist_defense:'Defesa Assistida'}[value]||titleCase(value))
const effectEmoji = (assets, type) => {
  const key = String(type || '').toLowerCase()
  const aliases = { tremor_burst:'tremor', amplitude_conversion_scorch:'tremor', self_bleed:'bleed', self_burn:'burn', consume_special_condition:'special_condition', false_hunger:'false_hunger', reuse_coin:'coin_active', make_unbreakable:'coin_unbreakable' }
  return assets?.[key]?.url || assets?.[aliases[key]]?.url || assets?.[key.replace(/_(burst|consumed|repressed)$/, '')]?.url || ''
}
const statusDescription = (type, potency, count, specialName) => ({
  burn: `No fim da rodada causa ${potency} de dano e perde 1 Count.`,
  bleed: `Ao usar moedas ofensivas, causa ${potency} por Count consumido.`,
  tremor: `Pode virar Tremor Burst; o Burst usa a Potência atual.`,
  rupture: `Ao sofrer dano, recebe ${potency} de dano e perde 1 Count.`,
  sinking: `Ao sofrer dano, perde ${potency} SP; em −45 SP, vira dano.`,
  poise: `Cada crítico recebe +${potency * 2}% de dano e consome 1 Count.`,
  charge: `Carga acumulada: Skills podem exigir ou gastar seus ${count} Count.`,
  haste: `Condição de velocidade usada por Skills e requisitos de efeito.`,
  special_condition: `${specialName}: efeito personalizado da ficha, sem regra automática.`,
}[type] || `Potência ${potency} e Count ${count} persistidos no combate.`)

export function snapshotToCharacter(snapshot) {
  const source = snapshot?.character
  if (!source) return null
  const appearance = snapshot.appearance || {}
  const profile = snapshot.profile || {}
  const specialEffectName = profile.special_effect_name || 'Efeito Trashholder'
  const statuses = (snapshot.statuses || []).map(item => ({
    id: item.status_type,
    name: item.status_type === 'special_condition' ? specialEffectName
      : item.status_type === 'tremor' && item.tremor_type === 'scorch' ? 'Tremor - Scorch'
      : titleCase(item.status_type),
    potency: item.potency,
    count: item.count,
    kind: 'negative',
    description: item.status_type === 'tremor' && item.tremor_type === 'scorch'
      ? 'Amplitude Conversion ativa: no Tremor Burst toma dano = (Tremor + Burn) ÷ 2 e perde 1 Burn Count.'
      : statusDescription(item.status_type, item.potency, item.count, specialEffectName),
    emoji: effectEmoji(snapshot.ui_assets, item.status_type),
  }))
  const skills = (snapshot.skills || []).slice().sort((a,b)=>slotRank(a.skill_slot)-slotRank(b.skill_slot)||a.name.localeCompare(b.name)).map((item, index) => ({
    id: item.name,
    slot: slotLabel(item.skill_slot,item.skill_type),
    skillSlot: item.skill_slot || '',
    name: item.name,
    basePower: item.base_power,
    coinPower: item.coin_power,
    coins: item.coins,
    coinTypes: {
      positive: Math.max(0, item.coin_power >= 0 ? item.coins : 0),
      negative: Math.max(0, item.coin_power < 0 ? item.coins : 0),
      unbreakable: (item.coin_layout || []).filter(coin => coin === 'unbreakable').length,
    },
    damageType: skillTypeLabel(item.skill_type || 'attack'),
    skillType: item.skill_type || 'attack',
    description: item.description || '',
    effects: (item.effects || []).map(effect => ({ ...effect, emoji: effectEmoji(snapshot.ui_assets, effect.effect_type) })),
  }))
  return {
    id: String(snapshot.user?.id || source.user_id || 'self'),
    ownerId: String(snapshot.user?.id || source.user_id || 'self'),
    themeId: 'theme-dossier-crimson',
    uptie: Number(profile.uptie || 1),
    level: Number(profile.level || 1),
    portrait: appearance.image_url || '/portraits/character-placeholder.svg',
    portraitState: 'normal',
    name: profile.identity?.name || source.name,
    title: appearance.subtitle || 'Identidade registrada',
    quote: appearance.footer_text || 'Ficha vinculada ao ClashBot.',
    hp: { current: Number(profile.hp || 0), maximum: Number(profile.max_hp || 0) },
    // O registro de combate é a fonte autoritativa: Clash e comandos alteram
    // este valor imediatamente, sem que um perfil antigo o sobrescreva.
    sp: { current: Number(source.sp ?? 0), maximum: 45 },
    stagger: { current: Number(profile.stagger || 0), maximum: Number(profile.max_stagger || 0) },
    light: { current: Number(profile.light || 0), maximum: Number(profile.max_light || 3) },
    offense: source.offense_level,
    defense: source.defense_level,
    rd: Number(profile.rd || 0),
    movement: Number(profile.movement || 9),
    identity: profile.identity || { age: '—', origin: '—', affiliation: '—', description: appearance.footer_text || 'Sem descrição registrada.', appearance: '—' },
    attributes: Object.entries(profile.attributes || {}).map(([name, value]) => ({name: titleCase(name), value})), proficiencies: profile.proficiencies || [], resistances: profile.resistances || [], statuses, skills,
    passives: profile.passives || [], inventory: profile.records?.inventory || [], notes: profile.records?.notes || [], relationships: profile.records?.relationships || [], memories: profile.records?.memories || [],
    specialEffectName,
    profile,
  }
}

export function ActivityDataProvider({ snapshot, auth, children }) {
  const value = useMemo(() => {
    const character = snapshotToCharacter(snapshot)
    const user = snapshot?.user || auth?.user || {}
    const role = {
      isMaster: Boolean(snapshot?.is_master),
      isOwner: true,
      canEditSheet: true,
      user: { id: String(user.id || ''), displayName: user.global_name || user.username || 'Jogador' },
    }
    return { character, role, uiAssets: snapshot?.ui_assets || {}, combatTargets: combatTargetsMock, combatLog: combatLogMock, enemies: enemiesMock, battleState: battleStateMock, themes: themesMock }
  }, [snapshot, auth])
  return <ActivityDataContext.Provider value={value}>{children}</ActivityDataContext.Provider>
}

export function useActivityData() {
  const value = useContext(ActivityDataContext)
  if (!value) throw new Error('ActivityDataProvider ausente.')
  return value
}
