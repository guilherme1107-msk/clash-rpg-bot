import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight, Plus, RadioTower, RefreshCw, Swords, Users } from 'lucide-react'

const phaseNames = { preparation: 'Preparação', declaration: 'Declaração', resolution: 'Resolução', complete: 'Concluída' }
const skillTypeNames = { attack: 'Ataque', guard: 'Defesa', evade: 'Evasiva', counter: 'Counter', clashable_guard: 'Defesa Clashável', clashable_counter: 'Counter Clashável', assist_defense: 'Defesa assistida' }

export function EncounterScreen({ onBack, loadEncounters, performAction }) {
  const [data, setData] = useState(null)
  const [channel, setChannel] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [freeEnemyId, setFreeEnemyId] = useState('')
  const [freeSkill, setFreeSkill] = useState('')
  const [freeTarget, setFreeTarget] = useState('')
  const [playerSkill, setPlayerSkill] = useState('')
  const [playerTarget, setPlayerTarget] = useState('')
  const [choices, setChoices] = useState({})
  const [actionMode, setActionMode] = useState('field')
  const [result, setResult] = useState(null)

  const load = async () => {
    try {
      const next = await loadEncounters()
      setData(next)
      setChannel(current => current || next.encounters[0]?.channel_id || '')
      if (!freeEnemyId && next.enemies[0]) setFreeEnemyId(next.enemies[0].id)
    } catch (caught) {
      setError(caught.message)
    }
  }

  useEffect(() => { load() }, [])

  const encounter = useMemo(() => data?.encounters.find(item => item.channel_id === channel), [data, channel])
  const freeEnemy = useMemo(() => data?.enemies.find(item => item.id === freeEnemyId), [data, freeEnemyId])
  const joined = encounter?.participants.find(item => item.is_self)
  const ownAttacks = useMemo(() => data?.skills?.filter(item => item.skill_type === 'attack') || [], [data?.skills])
  const ownClashSkills = useMemo(() => data?.skills || [], [data?.skills])
  const freeEnemyAttacks = useMemo(() => freeEnemy?.skills?.filter(item => item.type === 'attack') || [], [freeEnemy?.skills])

  useEffect(() => {
    const defaultTarget = encounter?.participants[0]?.user_id || ''
    setFreeTarget(current => current || defaultTarget)
    setPlayerTarget(current => current || data?.enemies[0]?.id || '')
    if (!playerSkill && ownAttacks[0]) setPlayerSkill(ownAttacks[0].name)
  }, [encounter?.participants, data?.enemies, ownAttacks, playerSkill])

  const act = async (payload) => {
    if (!encounter) return
    setBusy(true)
    setError('')
    try {
      const response = await performAction({ ...payload, channel_id: encounter.channel_id })
      if (response.result) setResult(response.result)
      await load()
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  const scheduleHostileAction = () => {
    const groupMemberId = String(freeEnemyId).startsWith('group:') ? Number(String(freeEnemyId).slice(6)) : 0
    const templateEnemyId = groupMemberId ? Number(freeEnemy?.template_enemy_id || 0) : Number(freeEnemyId)
    if (actionMode === 'field') {
      return act({ operation: 'add_action', enemy_id: templateEnemyId, enemy_group_member_id: groupMemberId, enemy_skill: freeSkill, target_user_id: freeTarget })
    }
    return act({ operation: 'add_enemy_free_attack', enemy_id: templateEnemyId, enemy_group_member_id: groupMemberId, enemy_skill: freeSkill, target_user_id: freeTarget, variant: actionMode })
  }

  if (!data) return <p className="empty-note">Carregando Encounter…</p>
  if (!data.encounters.length) return <section className="encounter-empty"><RadioTower /><h2>Nenhum Encounter ativo</h2></section>

  return <div className="encounter-screen">
    <header className="combat-screen-head">
      <button className="back-link" onClick={onBack}><ArrowLeft />Voltar</button>
      <div><p>CLASHBOT // OPERAÇÃO</p><h1>Encounter</h1></div>
      <button className="back-link" onClick={load}><RefreshCw />Atualizar</button>
    </header>
    {error && <p className="edit-error">{error}</p>}
    <nav className="encounter-tabs">
      {data.encounters.map(item => <button className={item.channel_id === channel ? 'active' : ''} onClick={() => setChannel(item.channel_id)} key={item.channel_id}>{item.name}</button>)}
    </nav>
    {encounter && <>
      <section className="encounter-command">
        <div><span>OPERAÇÃO</span><h2>{encounter.name}</h2></div>
        <div className={`phase phase-${encounter.phase}`}><span>TURNO {encounter.turn}</span><strong>{phaseNames[encounter.phase]}</strong></div>
        <div className="encounter-personal">
          {joined ? <b>{encounter.phase === 'complete' ? 'RODADA CONCLUÍDA · AGUARDANDO O MESTRE' : 'VOCÊ ESTÁ NO ENCOUNTER'}</b> : <button disabled={busy || !data.character} onClick={() => act({ operation: 'join' })}><Users />Entrar no Encounter</button>}
        </div>
      </section>

      {joined && encounter.phase === 'declaration' && <section className="unopposed-composer">
        <header><Swords /><div><span>ATAQUE LIVRE</span><small>Seu ataque sem oposição.</small></div></header>
        <select value={playerTarget} onChange={event => setPlayerTarget(event.target.value)}>{data.enemies.map(item => <option value={item.id} key={item.id}>{item.name}{item.kind === 'enemy_group_member' ? ` · ${item.hp}/${item.hp_max} HP · ${item.sp >= 0 ? '+' : ''}${item.sp} SP` : ''}</option>)}</select>
        <select value={playerSkill} onChange={event => setPlayerSkill(event.target.value)}><option value="">Escolher ataque…</option>{ownAttacks.map(item => <option value={item.name} key={item.name}>{item.name}</option>)}</select>
        <button disabled={busy || !playerSkill || !playerTarget} onClick={() => { const memberId = String(playerTarget).startsWith('group:') ? Number(String(playerTarget).slice(6)) : 0; const item = data.enemies.find(enemy => enemy.id === playerTarget); const enemyId = memberId ? Number(item?.template_enemy_id || 0) : Number(playerTarget); act({ operation: 'unopposed', enemy_id: enemyId, enemy_group_member_id: memberId, player_skill: playerSkill }) }}>Rolar ataque livre</button>
      </section>}

      {data.is_master && <section className="encounter-master">
        <header>
          <span>CONTROLE DO MESTRE</span>
          <div>
            <button disabled={busy || encounter.phase === 'preparation'} onClick={() => act({ operation: 'previous' })}><ChevronLeft />Fase anterior</button>
            <button disabled={busy || encounter.phase === 'complete'} onClick={() => act({ operation: 'advance' })}>Avançar<ChevronRight /></button>
            <button disabled={busy || encounter.phase !== 'complete'} onClick={() => act({ operation: 'next_turn' })}>Próximo turno</button>
          </div>
        </header>
      </section>}

      {data.is_master && encounter.phase === 'preparation' && <section className="enemy-free-composer">
        <header><Swords /><div><span>AÇÃO DO HOSTIL</span><small>{actionMode === 'field' ? 'Vai para o campo; se não receber Clash, ataca o alvo no fim da Declaração.' : 'Resolve automaticamente antes do próximo turno.'}</small></div></header>
        <select value={freeEnemyId} onChange={event => { setFreeEnemyId(event.target.value); setFreeSkill('') }}>{data.enemies.map(item => <option value={item.id} key={item.id}>{item.name}{item.kind === 'enemy_group_member' ? ` · ${item.hp}/${item.hp_max} HP · ${item.sp >= 0 ? '+' : ''}${item.sp} SP` : ''}</option>)}</select>
        <select key={freeEnemyId} value={freeSkill} onChange={event => setFreeSkill(event.target.value)}><option value="">Escolher Skill de ataque…</option>{freeEnemyAttacks.map(item => <option value={item.name} key={item.name}>{item.name}</option>)}</select>
        <select value={freeTarget} onChange={event => setFreeTarget(event.target.value)}><option value="">Escolher alvo…</option>{encounter.participants.map(item => <option value={item.user_id} key={item.user_id}>{item.character_name}</option>)}</select>
        <select value={actionMode} onChange={event => setActionMode(event.target.value)}><option value="field">No campo · pode Clash</option><option value="unopposed">Ataque livre · sem oposição</option><option value="follow_up">Ataque livre · Follow-up</option></select>
        <button disabled={busy || !freeSkill || !freeTarget} onClick={scheduleHostileAction}><Plus />{actionMode === 'field' ? 'Colocar no campo' : 'Agendar'}</button>
        {encounter.enemy_free_actions?.filter(action => action.status === 'pending').map(action => {
          const scheduledEnemy = data.enemies.find(item => item.id === (action.enemy_group_member_id ? `group:${action.enemy_group_member_id}` : action.enemy_id))?.name || 'Hostil'
          const scheduledTarget = encounter.participants.find(item => item.user_id === action.target_user_id)?.character_name || 'alvo'
          return <div className="enemy-free-entry" key={action.id}>◆ Agendado: <b>{scheduledEnemy}</b> usa <b>{action.enemy_skill}</b> em <b>{scheduledTarget}</b> · {action.variant === 'follow_up' ? 'Follow-up' : 'Sem oposição'}</div>
        })}
      </section>}

      <div className="encounter-grid">
        <section>
          <header className="encounter-section-title"><Users /><div><span>PARTICIPANTES</span></div></header>
          <div className="participant-list">{encounter.participants.map(item => <article key={item.user_id}><strong>{item.character_name}</strong><b>{item.ready ? 'PRONTO' : 'PENDENTE'}</b></article>)}</div>
        </section>
        <section>
          <header className="encounter-section-title"><Swords /><div><span>AÇÕES NO CAMPO</span></div></header>
          <div className="field-action-list">
            {encounter.actions.map(action => {
              const targetParticipant = encounter.participants.find(item => item.user_id === action.target_user_id)
              const targetName = targetParticipant?.character_name || 'alvo não definido'
              const actionSkills = ownClashSkills
              return <article key={action.id}>
                <header><span>#{action.id} · {action.enemy_name}{action.enemy_group_member_id ? ' · integrante do grupo' : ''}</span><b>{action.status}</b></header>
                <h3>{action.enemy_skill}</h3><small>Alvo: {targetName}</small>
                {action.status === 'open' && encounter.phase === 'declaration' && (joined || data.is_master) && <div>
                  <select value={choices[action.id] || ''} onChange={event => setChoices(current => ({ ...current, [action.id]: event.target.value }))}><option value="">Escolher Skill para Clash…</option>{actionSkills.map(item => <option value={item.name} key={item.name}>{item.name} · {skillTypeNames[item.skill_type] || item.skill_type}</option>)}</select>
                  <button disabled={busy || !choices[action.id]} onClick={() => act({ operation: 'resolve', action_id: action.id, player_skill: choices[action.id] })}>Puxar Clash</button>
                </div>}
              </article>
            })}
          </div>
        </section>
      </div>
      {result && <section className="encounter-result"><h2>{result.left_name} atacou {result.right_name}</h2><strong>{result.damage} DANO</strong></section>}
    </>}
  </div>
}
