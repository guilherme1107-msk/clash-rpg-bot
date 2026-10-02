import { useEffect, useState } from 'react'
import { ArrowLeft, BookUser, Crosshair, Plus, RefreshCw, Settings, Skull, Swords, Trash2, Users } from 'lucide-react'
import { SkillsTab } from '../sheet/SkillsTab'

const tabs = [['characters', 'Fichas', BookUser], ['enemies', 'Hostis', Skull], ['groups', 'Grupos', Users], ['battles', 'Batalhas', Swords], ['settings', 'Configurações', Settings]]
const statusOptions = ['burn','bleed','tremor','rupture','sinking','poise','charge','haste','special_condition']
const nice = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, item => item.toUpperCase())
const viewSkills = (skills = [], assets = {}) => skills.map((item, index) => ({
  id: item.name, slot: `Skill ${index + 1}`, name: item.name,
  basePower: item.base_power, coinPower: item.coin_power, coins: item.coins,
  coinTypes: { positive: item.coin_power >= 0 ? item.coins : 0, negative: item.coin_power < 0 ? item.coins : 0, unbreakable: (item.coin_layout || []).filter(coin => coin === 'unbreakable').length },
  damageType: nice(item.skill_type || 'attack'), description: item.description || '',
  effects: (item.effects || []).map(effect => ({ ...effect, emoji: assets?.[effect.effect_type]?.url || '' })),
}))

function ImageSlot({ imageUrl, label, onImage }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const accept = async file => { if (!file) return; if (!file.type.startsWith('image/')) { setError('Cole uma imagem.'); return } if (file.size > 8*1024*1024) { setError('Máximo de 8 MB.'); return }; setBusy(true); setError(''); try { const data = await new Promise((resolve,reject)=>{const reader=new FileReader(); reader.onload=()=>resolve(reader.result); reader.onerror=reject; reader.readAsDataURL(file)}); await onImage(data) } catch(cause) { setError(cause.message || 'Não foi possível salvar a imagem.') } finally { setBusy(false) } }
  return <label className="enemy-image-slot" onPaste={event=>{const file=[...(event.clipboardData?.files||[])][0]; if(file){event.preventDefault();accept(file)}}}><input type="file" accept="image/png,image/jpeg,image/gif,image/webp" onChange={event=>accept(event.target.files?.[0])}/>{imageUrl?<img src={imageUrl} alt=""/>:<span>SEM IMAGEM</span>}<b>{busy?'SALVANDO…':label}</b><small>Clique para enviar ou cole com Ctrl+V</small>{error&&<em>{error}</em>}</label>
}

function EnemySheetEditor({ detail, set, setStatus, save, saving, removeEnemy, createGroup, saveSkill, deleteSkill, onImage }) {
  const [tab, setTab] = useState('overview')
  return <section className="enemy-dossier admin-editor">
    <header><div><span>FICHA-BASE HOSTIL // EDITÁVEL</span><h2>{detail.name}</h2><small>O molde define Skills, atributos e efeitos. HP e SP de combate pertencem a cada integrante do grupo.</small></div><span className="enemy-sheet-mark">HOSTIL</span></header>
    <nav className="enemy-sheet-tabs"><button className={tab==='overview'?'active':''} onClick={()=>setTab('overview')}>Visão Geral</button><button className={tab==='skills'?'active':''} onClick={()=>setTab('skills')}>Skills</button></nav>
    {tab==='overview' ? <>
      <ImageSlot imageUrl={detail.appearance?.image_url} label="IMAGEM DO HOSTIL" onImage={onImage}/>
      <div className="enemy-vitals"><article><span>VIDA</span><strong>POR INTEGRANTE</strong><small>Configurada dentro do grupo</small></article><article><span>SANIDADE-BASE</span><strong>{detail.sp >= 0 ? '+' : ''}{detail.sp}</strong><small>Limite −45 a +45</small></article><article><span>OFFENSE</span><strong>{detail.offense_level}</strong></article><article><span>DEFENSE</span><strong>{detail.defense_level}</strong></article></div>
      <div className="admin-edit-grid"><label>Nome da ficha-base<input value={detail.name} onChange={e => set('name', e.target.value)} /></label><label>Sanidade-base<input type="number" min="-45" max="45" value={detail.sp} onChange={e => set('sp', Number(e.target.value))} /></label><label>Offense<input type="number" value={detail.offense_level} onChange={e => set('offense_level', Number(e.target.value))} /></label><label>Defense<input type="number" value={detail.defense_level} onChange={e => set('defense_level', Number(e.target.value))} /></label><label>Paralisia<input type="number" min="0" value={detail.paralysis} onChange={e => set('paralysis', Number(e.target.value))} /></label></div>
      <div className="admin-modifier-grid"><label>Base Power Mod<input type="number" value={detail.base_power_mod || 0} onChange={e => set('base_power_mod', Number(e.target.value))} /></label><label>Coin Power Mod<input type="number" value={detail.coin_power_mod || 0} onChange={e => set('coin_power_mod', Number(e.target.value))} /></label><label>Clash Power Mod<input type="number" value={detail.clash_power_mod || 0} onChange={e => set('clash_power_mod', Number(e.target.value))} /></label><label>Offense Mod<input type="number" value={detail.offense_level_mod || 0} onChange={e => set('offense_level_mod', Number(e.target.value))} /></label><label>Defense Mod<input type="number" value={detail.defense_level_mod || 0} onChange={e => set('defense_level_mod', Number(e.target.value))} /></label></div>
      <div className="admin-status-editor"><header><span>EFEITOS ATIVOS DO MOLDE</span><button onClick={() => set('statuses', [...detail.statuses, { status_type: 'bleed', potency: 1, count: 1 }])}>+ Efeito</button></header>{detail.statuses.length===0&&<p className="empty-note">Sem efeitos ativos no molde.</p>}{detail.statuses.map((item, index) => <div key={index}><select value={item.status_type} onChange={e => setStatus(index, 'status_type', e.target.value)}>{statusOptions.map(type=><option value={type} key={type}>{type.replaceAll('_',' ').toUpperCase()}</option>)}</select><input type="number" aria-label="Potência" value={item.potency} onChange={e => setStatus(index, 'potency', Number(e.target.value))} /><input type="number" aria-label="Quantidade" value={item.count} onChange={e => setStatus(index, 'count', Number(e.target.value))} /><button onClick={() => set('statuses', detail.statuses.filter((_, i) => i !== index))}>×</button></div>)}</div>
      <footer><button className="admin-group-create" onClick={createGroup}><Users />Criar grupo por esta ficha</button><button className="danger" onClick={removeEnemy}><Trash2 />Excluir hostil</button><button onClick={save} disabled={saving}>{saving ? 'Salvando…' : 'Salvar visão geral'}</button></footer>
    </> : <div className="enemy-skills-panel"><header><span>ARSENAL DO HOSTIL</span><small>As Skills criadas aqui serão usadas por cada integrante deste grupo.</small></header><SkillsTab skills={detail.skills} onSave={saveSkill} onDelete={deleteSkill} /></div>}
  </section>
}

export function MasterDashboard({ onBack, loadAdmin, loadEntity, saveEntity, skillAction, enemyAction, battleAction, imageAction, saveSettings }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('characters')
  const [detail, setDetail] = useState(null)
  const [groupDetail, setGroupDetail] = useState(null)
  const [saving, setSaving] = useState(false)
  const [modal, setModal] = useState(null)
  const [notice, setNotice] = useState('')
  const [auditChannelId, setAuditChannelId] = useState('')
  const load = () => { setError(''); return loadAdmin().then(res => { setData(res); if (res.settings?.audit_channel_id) setAuditChannelId(res.settings.audit_channel_id) }).catch(item => setError(item.message)) }
  useEffect(() => { load() }, [])

  const loadDetail = async (kind, owner_id) => {
    const value = await loadEntity(kind, owner_id)
    setDetail({ ...value.entity, kind, owner_id: String(owner_id), statuses: value.statuses, skills: viewSkills(value.skills, value.ui_assets), uiAssets: value.ui_assets || {}, appearance: value.appearance || {} })
  }
  const open = async item => {
    if (tab === 'battles' || tab === 'groups') return
    setError('')
    try { await loadDetail(tab === 'enemies' ? 'enemy' : 'player', item.id || item.user_id) }
    catch (cause) { setError(cause.message) }
  }
  const openGroup = async item => {
    setError('')
    try { const value = await enemyAction({ operation: 'group_detail', group_id: item.id }); setGroupDetail(value) }
    catch (cause) { setError(cause.message) }
  }
  const refreshGroup = async () => { if (groupDetail) await openGroup(groupDetail.group) }
  const updateMember = async member => { try { await enemyAction({ operation: 'group_update_member', member_id: member.id, member }); await refreshGroup() } catch (cause) { setError(cause.message) } }
  const setMemberStatuses = (memberId, statuses) => setGroupDetail(current => ({...current,members:current.members.map(member=>member.id===memberId?{...member,statuses}:member)}))
  const saveMemberStatuses = async member => { try { await enemyAction({operation:'group_save_statuses',member_id:member.id,statuses:member.statuses||[]}); await refreshGroup(); setNotice(`Efeitos de ${member.member_name} salvos.`) } catch(cause) { setError(cause.message) } }
  const addGroupMembers = () => setModal({ type: 'add-members', title: 'Adicionar integrantes', values: { quantity: 1 } })
  const removeGroupMember = async member => { try { await enemyAction({ operation: 'group_remove_member', member_id: member.id }); await refreshGroup(); await load(); setNotice(`${member.member_name} foi removido.`) } catch (cause) { setError(cause.message) } }
  const set = (key, value) => setDetail(current => ({ ...current, [key]: value }))
  const setStatus = (index, key, value) => setDetail(current => ({ ...current, statuses: current.statuses.map((item, i) => i === index ? { ...item, [key]: value } : item) }))
  const save = async () => {
    setSaving(true); setError('')
    try { await saveEntity(detail); setDetail(null); await load() }
    catch (cause) { setError(cause.message) }
    finally { setSaving(false) }
  }
  const saveSkill = async skill => {
    await skillAction({ operation: 'save', kind: detail.kind, owner_id: detail.owner_id, skill })
    await loadDetail(detail.kind, detail.owner_id); await load()
  }
  const deleteSkill = async name => {
    await skillAction({ operation: 'delete', kind: detail.kind, owner_id: detail.owner_id, name })
    await loadDetail(detail.kind, detail.owner_id); await load()
  }
  const uploadEnemyImage = async data => { if (!detail) return; const result = await imageAction({owner_kind:'enemy',owner_id:detail.owner_id,data}); setDetail(current=>({...current,appearance:{...(current.appearance||{}),image_url:result.image_url}})); setNotice('Imagem do hostil atualizada.') }
  const uploadGroupImage = async data => { if (!groupDetail) return; const result = await imageAction({owner_kind:'enemy_group',owner_id:groupDetail.group.id,data}); setGroupDetail(current=>({...current,appearance:{...(current.appearance||{}),image_url:result.image_url}})); setNotice('Imagem do grupo atualizada.') }
  const createEnemy = () => setModal({ type: 'enemy', title: 'Criar ficha-base hostil', values: { name: '' } })
  const removeEnemy = async () => {
    if (!confirm(`Excluir ${detail.name} e suas Skills?`)) return
    try { await enemyAction({ operation: 'delete', owner_id: detail.owner_id }); setDetail(null); await load() } catch (cause) { setError(cause.message) }
  }
  const createGroup = () => setModal({ type: 'group', title: 'Criar grupo hostil', values: { name: `${detail.name} — Grupo`, quantity: 3, hp_max: 100 } })
  const newBattle = () => setModal({ type: 'battle', title: 'Iniciar Encounter', values: { channel_id: '', name: 'Novo Encontro' } })
  const submitModal = async event => {
    event.preventDefault(); if (!modal) return
    const values = modal.values || {}; setSaving(true); setError(''); setNotice('')
    try {
      if (modal.type === 'enemy') { if (!String(values.name || '').trim()) throw new Error('Informe o nome da ficha-base.'); await enemyAction({ operation: 'create', name: values.name }) }
      if (modal.type === 'group') { await enemyAction({ operation: 'create_group', template_enemy_id: detail.owner_id, name: values.name, quantity: values.quantity, hp_max: values.hp_max }) }
      if (modal.type === 'add-members') { await enemyAction({ operation: 'group_add_members', group_id: groupDetail.group.id, quantity: values.quantity }); await refreshGroup() }
      if (modal.type === 'battle') { if (!String(values.channel_id || '').trim()) throw new Error('Informe o ID do canal.'); await battleAction({ operation: 'start', channel_id: values.channel_id, name: values.name }) }
      await load(); setModal(null); setNotice('Ação concluída com sucesso.')
    } catch (cause) { setError(cause.message || 'Não foi possível concluir esta ação.') }
    finally { setSaving(false) }
  }
  const battle = async (item, operation) => {
    try { await battleAction({ operation, channel_id: item.channel_id }); await load() } catch (cause) { setError(cause.message) }
  }
  const rows = data?.[tab] || []

  return <div className="master-dashboard">
    <header className="combat-screen-head"><button className="back-link" onClick={onBack}><ArrowLeft />Voltar</button><div><p>CLASHBOT // ADMINISTRAÇÃO</p><h1>Central do Mestre</h1></div><button className="back-link" onClick={load}><RefreshCw />Atualizar</button></header>
    {error && <p className="edit-error">{error}</p>}{notice && <p className="admin-notice">{notice}</p>}
    {!data ? <p className="empty-note">Carregando…</p> : <>
      <div className="admin-metrics"><span><b>{data.characters.length}</b> Fichas</span><span><b>{data.enemies.length}</b> Fichas-base</span><span><b>{data.groups?.length||0}</b> Grupos</span><span><b>{data.battles.length}</b> Batalhas ativas</span></div>
      <nav className="admin-tabs">{tabs.map(([id, label, Icon]) => <button className={tab === id ? 'active' : ''} key={id} onClick={() => { setTab(id); setDetail(null); setGroupDetail(null) }}><Icon />{label}</button>)}</nav>
      <section className="admin-section"><header><Crosshair /><div><span>{tabs.find(item => item[0] === tab)[1].toUpperCase()}</span><small>{tab === 'settings' ? 'CONFIGURAÇÕES DO SERVIDOR' : `${rows.length} REGISTROS`}</small></div>{tab === 'enemies' && <button className="admin-add" onClick={createEnemy}><Plus />Criar hostil</button>}{tab === 'battles' && <button className="admin-add" onClick={newBattle}><Plus />Iniciar batalha</button>}</header>
        {tab === 'settings' ? <form className="admin-editor" onSubmit={async e => { e.preventDefault(); setSaving(true); setError(''); setNotice(''); try { await saveSettings({ audit_channel_id: auditChannelId }); setNotice('Configurações salvas com sucesso!') } catch(cause) { setError(cause.message) } finally { setSaving(false) } }}><div className="admin-edit-grid"><label style={{gridColumn:'span 2'}}>ID do Canal de Resultados do Bot (Auditoria / Clash)<input value={auditChannelId} placeholder="Ex: 1536852944518127748" onChange={e => setAuditChannelId(e.target.value)} /><small style={{display:'block',marginTop:'4px',opacity:0.7}}>Quando um Clash for executado pela Activity sem canal especificado, os resultados serão lançados neste canal do Discord.</small></label></div><footer><button type="submit" disabled={saving}>{saving ? 'Salvando…' : 'Salvar configurações'}</button></footer></form> : <div className="admin-roster">{rows.length ? rows.map(item => tab === 'battles' ? <article className="admin-battle-row" key={item.channel_id}><div><strong>{item.name}</strong><span>Canal {item.channel_id} · Turno {item.turn} · {item.phase}</span></div><div><button onClick={() => battle(item, 'previous')}>◀</button><button onClick={() => battle(item, 'advance')}>Avançar</button><button onClick={() => battle(item, 'next_turn')}>Turno +</button><button onClick={() => confirm('Encerrar esta batalha?') && battle(item, 'end')}>■</button></div></article> : tab === 'groups' ? <article className="admin-group-row clickable" onClick={() => openGroup(item)} key={item.id}><strong>{item.name}</strong><span>Ficha-base: {item.template_name} · {item.members} inimigos independentes</span></article> : <article className="clickable" onClick={() => open(item)} key={item.user_id || item.id}><strong>{item.name}</strong><span>SP {item.sp >= 0 ? '+' : ''}{item.sp} · OFF {item.offense_level} · DEF {item.defense_level} · {item.skills} Skills</span></article>) : <p className="empty-note">Nenhum registro.</p>}</div>}
      </section>
      {detail && (detail.kind === 'enemy' ? <EnemySheetEditor detail={detail} set={set} setStatus={setStatus} save={save} saving={saving} removeEnemy={removeEnemy} createGroup={createGroup} saveSkill={saveSkill} deleteSkill={deleteSkill} onImage={uploadEnemyImage} /> : <section className="admin-editor">
        <header><div><span>EDIÇÃO ADMINISTRATIVA</span><h2>{detail.name}</h2></div><button onClick={() => setDetail(null)}>×</button></header>
        <div className="admin-edit-grid"><label>Nome<input value={detail.name} onChange={e => set('name', e.target.value)} /></label><label>Sanidade<input type="number" min="-45" max="45" value={detail.sp} onChange={e => set('sp', Number(e.target.value))} /></label><label>Offense<input type="number" value={detail.offense_level} onChange={e => set('offense_level', Number(e.target.value))} /></label><label>Defense<input type="number" value={detail.defense_level} onChange={e => set('defense_level', Number(e.target.value))} /></label><label>Paralisia<input type="number" min="0" value={detail.paralysis} onChange={e => set('paralysis', Number(e.target.value))} /></label></div>
        <div className="admin-modifier-grid"><label>Base Power Mod<input type="number" value={detail.base_power_mod || 0} onChange={e => set('base_power_mod', Number(e.target.value))} /></label><label>Coin Power Mod<input type="number" value={detail.coin_power_mod || 0} onChange={e => set('coin_power_mod', Number(e.target.value))} /></label><label>Clash Power Mod<input type="number" value={detail.clash_power_mod || 0} onChange={e => set('clash_power_mod', Number(e.target.value))} /></label><label>Offense Mod<input type="number" value={detail.offense_level_mod || 0} onChange={e => set('offense_level_mod', Number(e.target.value))} /></label><label>Defense Mod<input type="number" value={detail.defense_level_mod || 0} onChange={e => set('defense_level_mod', Number(e.target.value))} /></label></div>
        <div className="admin-status-editor"><header><span>EFEITOS ATIVOS {detail.kind==='enemy'?'DO HOSTIL':''}</span><button onClick={() => set('statuses', [...detail.statuses, { status_type: 'bleed', potency: 1, count: 1 }])}>+ Efeito</button></header>{detail.statuses.length===0&&<p className="empty-note">Sem efeitos ativos. Adicione um efeito para ele aparecer no Encounter.</p>}{detail.statuses.map((item, index) => <div key={index}><select value={item.status_type} onChange={e => setStatus(index, 'status_type', e.target.value)}>{statusOptions.map(type=><option value={type} key={type}>{type.replaceAll('_',' ').toUpperCase()}</option>)}</select><input type="number" aria-label="Potência" value={item.potency} onChange={e => setStatus(index, 'potency', Number(e.target.value))} /><input type="number" aria-label="Quantidade" value={item.count} onChange={e => setStatus(index, 'count', Number(e.target.value))} /><button onClick={() => set('statuses', detail.statuses.filter((_, i) => i !== index))}>×</button></div>)}</div>
        <footer>{detail.kind === 'enemy' && <><button className="admin-group-create" onClick={createGroup}><Users />Criar grupo por esta ficha</button><button className="danger" onClick={removeEnemy}><Trash2 />Excluir hostil</button></>}<button onClick={save} disabled={saving}>{saving ? 'Salvando…' : 'Salvar atributos e status'}</button></footer>
        <div className="admin-skills"><header><span>ARSENAL DA FICHA</span><small>Crie e edite Skills sem sair da visão do mestre.</small></header><SkillsTab skills={detail.skills} onSave={saveSkill} onDelete={deleteSkill} /></div>
      </section>)}
      {groupDetail && <section className="group-member-effects"><header><span>EFEITOS DOS INTEGRANTES</span><small>Estes efeitos são individuais e usam os efeitos reais do bot.</small></header>{groupDetail.members.map(member=><article key={member.id}><h3>{member.member_name}</h3><div>{(member.statuses||[]).map((status,index)=><p key={index}><select value={status.status_type} onChange={event=>setMemberStatuses(member.id,member.statuses.map((item,i)=>i===index?{...item,status_type:event.target.value}:item))}>{statusOptions.map(type=><option value={type} key={type}>{nice(type)}</option>)}</select><input type="number" min="0" value={status.potency} onChange={event=>setMemberStatuses(member.id,member.statuses.map((item,i)=>i===index?{...item,potency:Number(event.target.value)}:item))}/><input type="number" min="0" value={status.count} onChange={event=>setMemberStatuses(member.id,member.statuses.map((item,i)=>i===index?{...item,count:Number(event.target.value)}:item))}/><button onClick={()=>setMemberStatuses(member.id,member.statuses.filter((_,i)=>i!==index))}>×</button></p>)}<button onClick={()=>setMemberStatuses(member.id,[...(member.statuses||[]),{status_type:'bleed',potency:1,count:1}])}>+ Efeito</button><button onClick={()=>saveMemberStatuses(member)}>Salvar efeitos</button></div></article>)}</section>}
      {groupDetail && <div className="group-sheet-extras"><ImageSlot imageUrl={groupDetail.appearance?.image_url} label="IMAGEM DO GRUPO" onImage={uploadGroupImage}/><section className="group-inherited-skills"><header><span>SKILLS HERDADAS</span><small>As Skills vêm da ficha-base.</small></header>{groupDetail.skills?.length ? <div>{groupDetail.skills.map(skill=><article key={skill.name}><b>{skill.name}</b><span>{nice(skill.skill_type)} · Base {skill.base_power} · Coin {skill.coin_power>=0?'+':''}{skill.coin_power} · {skill.coins} moeda(s)</span></article>)}</div> : <p className="empty-note">A ficha-base ainda não possui Skills.</p>}</section></div>}
      {groupDetail && <section className="admin-editor group-editor"><header><div><span>GRUPO HOSTIL</span><h2>{groupDetail.group.name}</h2><small>Ficha-base: {groupDetail.group.template_name} · OFF {groupDetail.group.offense_level} · DEF {groupDetail.group.defense_level}</small></div><button onClick={() => setGroupDetail(null)}>×</button></header><div className="group-editor-actions"><button onClick={addGroupMembers}><Users />Adicionar integrantes</button><small>Cada integrante possui HP, SP e modificadores próprios.</small></div><div className="group-member-list">{groupDetail.members.map(member=><article key={member.id}><header><input value={member.member_name} onChange={event=>setGroupDetail(current=>({...current,members:current.members.map(item=>item.id===member.id?{...item,member_name:event.target.value}:item)}))} /><button className="danger" onClick={()=>removeGroupMember(member)}><Trash2 /></button></header><div><label>HP<input type="number" min="0" value={member.hp} onChange={event=>setGroupDetail(current=>({...current,members:current.members.map(item=>item.id===member.id?{...item,hp:Number(event.target.value)}:item)}))} /></label><label>HP Máx.<input type="number" min="1" value={member.hp_max} onChange={event=>setGroupDetail(current=>({...current,members:current.members.map(item=>item.id===member.id?{...item,hp_max:Number(event.target.value)}:item)}))} /></label><label>SP<input type="number" min="-45" max="45" value={member.sp} onChange={event=>setGroupDetail(current=>({...current,members:current.members.map(item=>item.id===member.id?{...item,sp:Number(event.target.value)}:item)}))} /></label><label>Paralisia<input type="number" min="0" value={member.paralysis} onChange={event=>setGroupDetail(current=>({...current,members:current.members.map(item=>item.id===member.id?{...item,paralysis:Number(event.target.value)}:item)}))} /></label><button onClick={()=>updateMember(member)}>Salvar integrante</button></div></article>)}</div></section>}
      {modal && <div className="admin-modal-backdrop"><form className="admin-modal" onSubmit={submitModal}><header><div><span>CLASHBOT // CENTRAL</span><h2>{modal.title}</h2></div><button type="button" onClick={() => setModal(null)}>×</button></header>{modal.type === 'enemy' && <label>Nome da ficha-base<input autoFocus value={modal.values.name} onChange={event=>setModal(current=>({...current,values:{...current.values,name:event.target.value}}))}/></label>}{modal.type === 'group' && <><label>Nome do grupo<input autoFocus value={modal.values.name} onChange={event=>setModal(current=>({...current,values:{...current.values,name:event.target.value}}))}/></label><div className="admin-modal-grid"><label>Quantidade<input type="number" min="1" max="20" value={modal.values.quantity} onChange={event=>setModal(current=>({...current,values:{...current.values,quantity:Number(event.target.value)}}))}/></label><label>HP máximo<input type="number" min="1" value={modal.values.hp_max} onChange={event=>setModal(current=>({...current,values:{...current.values,hp_max:Number(event.target.value)}}))}/></label></div></>}{modal.type === 'add-members' && <label>Quantidade<input autoFocus type="number" min="1" max="20" value={modal.values.quantity} onChange={event=>setModal(current=>({...current,values:{...current.values,quantity:Number(event.target.value)}}))}/></label>}{modal.type === 'battle' && <><label>ID do canal<input autoFocus inputMode="numeric" value={modal.values.channel_id} onChange={event=>setModal(current=>({...current,values:{...current.values,channel_id:event.target.value}}))}/></label><label>Nome do Encounter<input value={modal.values.name} onChange={event=>setModal(current=>({...current,values:{...current.values,name:event.target.value}}))}/></label></>}<footer><button type="button" onClick={() => setModal(null)}>Cancelar</button><button type="submit" disabled={saving}>{saving ? 'Processando…' : 'Confirmar'}</button></footer></form></div>}
    </>}
  </div>
}
