import { Component, lazy, Suspense, useEffect, useState } from 'react'
import { Activity, RadioTower, RefreshCw, ShieldHalf, Swords } from 'lucide-react'
import { adminBattleAction, adminEnemyAction, adminSkillAction, authenticateActivity, deleteOwnSkill, encounterAction, loadAdminEntity, loadAdminOverview, loadCombatTargets, loadEncounters, loadOwnSheet, resolveActivityClash, saveAdminEntity, saveAdminSettings, saveOwnProfile, saveOwnSkill, saveOwnStatuses, uploadAdminImage } from './discord'
import { ActivityDataProvider, useActivityData } from './activityData'
import { ThemeProvider } from './theme/ThemeProvider'
import { useRole } from './hooks/useRole'
import { useHashRoute } from './hooks/useHashRoute'
import { Topbar } from './components/layout/Topbar'
import { Footer } from './components/layout/Footer'
import { PortraitPanel } from './components/layout/PortraitPanel'
import { UptieDisplay } from './components/sheet/UptieDisplay'
import { OverviewTab } from './components/sheet/OverviewTab'
const CombatScreen = lazy(() => import('./components/combat/CombatScreen').then(module => ({default: module.CombatScreen})))
const MasterDashboard = lazy(() => import('./components/master/MasterDashboard').then(module => ({default: module.MasterDashboard})))
const SheetScreen = lazy(() => import('./components/sheet/SheetScreen').then(module => ({default: module.SheetScreen})))
const EncounterScreen = lazy(() => import('./components/encounter/EncounterScreen').then(module => ({default: module.EncounterScreen})))

function Loading({ error }) {
  return <main className="loading boot-screen"><section className="boot-card"><img className="boot-logo" src="./assets/clashbot-logo.png" alt="ClashBot"/><p className="boot-kicker">CLASHBOT // DISCORD ACTIVITY</p><h1 className={`boot-title${error ? ' boot-title-error' : ''}`}>{error ? 'VÍNCULO INTERROMPIDO' : 'CLASHBOT'}</h1><span className="boot-status">{error || 'Sincronizando identidade…'}</span>{!error && <div className="boot-line" />}{error && <button className="boot-retry" onClick={() => location.reload()}><RefreshCw /> Reconectar</button>}</section></main>
}

class ActivityErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <main className="loading"><Activity /><p>CLASHBOT // ERRO DE INTERFACE</p><h1>Falha ao carregar o painel</h1><span>{this.state.error.message || 'Erro desconhecido.'}</span><button onClick={() => location.reload()}><RefreshCw /> Tentar novamente</button></main>
    return this.props.children
  }
}

function Shell({ onProfileSaved, onStatusSaved, onSkillSaved, onSkillDeleted, loadAdmin, loadAdminEntityData, saveAdminEntityData, adminSkill, enemyAction, battleAction, imageAction, saveSettings, loadTargets, resolveClash, loadEncounterData, runEncounterAction }) {
  const role = useRole()
  const { character } = useActivityData()
  const { route, navigate } = useHashRoute()
  const render = () => route === '/combat' ? <CombatScreen onBack={() => navigate('/')} loadTargets={loadTargets} resolveClash={resolveClash} /> : route === '/encounter' ? <EncounterScreen onBack={() => navigate('/')} loadEncounters={loadEncounterData} performAction={runEncounterAction} /> : route === '/master' && role.isMaster ? <MasterDashboard onBack={() => navigate('/')} loadAdmin={loadAdmin} loadEntity={loadAdminEntityData} saveEntity={saveAdminEntityData} skillAction={adminSkill} enemyAction={enemyAction} battleAction={battleAction} imageAction={imageAction} saveSettings={saveSettings} /> : <SheetScreen bare onProfileSaved={onProfileSaved} onStatusSaved={onStatusSaved} onSkillSaved={onSkillSaved} onSkillDeleted={onSkillDeleted} />
  return <div className={`rosemary-shell${route === '/encounter' ? ' encounter-mode' : ''}`}><div className="grain"/><header className="dossier-topbar"><div className="sinner-mark clashbot-header-logo"><img src="./assets/clashbot-logo.png" alt="ClashBot"/></div><div><p>CLASHBOT // DOSSIÊ DE CAMPO</p><h1>{character.name} <i>{character.title}</i></h1></div><div className="dossier-actions"><button title="Clash livre" onClick={() => navigate('/combat')}><Swords /></button><button title="Encounter" onClick={() => navigate('/encounter')}><RadioTower /></button>{role.isMaster && <button title="Painel do mestre" onClick={() => navigate('/master')}><ShieldHalf /></button>}<span>{role.isMaster ? 'MESTRE' : 'VÍNCULO ATIVO'}</span></div></header><div className="dossier-layout"><aside className="dossier-portrait"><div className="serial">IDENTIDADE // {character.id.slice(-4)}</div><PortraitPanel character={character}/>{route === '/encounter' && <div className="encounter-side-overview"><OverviewTab character={character} onSave={onProfileSaved}/></div>}</aside><section className="dossier-console"><div className="dossier-summary"><div><span>ESTADO MENTAL</span><strong>{character.sp.current >= 45 ? '+45 // ÊXTASE' : character.sp.current <= -45 ? '-45 // COLAPSO' : `${character.sp.current >= 0 ? '+' : ''}${character.sp.current} // CONTIDO`}</strong></div><div><span>CLASSIFICAÇÃO</span><strong>{character.title}</strong></div></div><UptieDisplay current={character.uptie}/><Suspense fallback={<p className="empty-note">Carregando módulo…</p>}>{render()}</Suspense></section></div><Footer /></div>
}

export default function App() {
  const [session, setSession] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { authenticateActivity().then(setSession).catch(item => setError(item.message)) }, [])
  useEffect(() => { if (!session) return; const controller = new AbortController(); loadOwnSheet(session.accessToken, session.guildId, controller.signal).then(setSnapshot).catch(item => setError(item.message)); return () => controller.abort() }, [session])
  if (error || !snapshot) return <Loading error={error} />
  if (!snapshot.character) return <main className="loading"><Activity /><h1>Nenhuma ficha encontrada</h1><span>{snapshot.message || 'Crie sua ficha no ClashBot.'}</span></main>
  const refresh = async () => setSnapshot(await loadOwnSheet(session.accessToken, snapshot.guild_id))
  const persistProfile = async profile => { await saveOwnProfile(session.accessToken, snapshot.guild_id, profile); const refreshed = await loadOwnSheet(session.accessToken, snapshot.guild_id); setSnapshot(refreshed); return refreshed.profile }
  const persistSkill = async skill => { await saveOwnSkill(session.accessToken, snapshot.guild_id, skill); await refresh() }
  const persistStatuses = async statuses => { await saveOwnStatuses(session.accessToken,snapshot.guild_id,statuses); await refresh() }
  const removeSkill = async name => { await deleteOwnSkill(session.accessToken, snapshot.guild_id, name); await refresh() }
  const admin = () => loadAdminOverview(session.accessToken, snapshot.guild_id)
  const adminEntity = (kind,id) => loadAdminEntity(session.accessToken,snapshot.guild_id,kind,id)
  const adminSave = payload => saveAdminEntity(session.accessToken,snapshot.guild_id,payload)
  const skillAdmin = payload => adminSkillAction(session.accessToken,snapshot.guild_id,payload)
  const enemyAdmin = payload => adminEnemyAction(session.accessToken,snapshot.guild_id,payload)
  const battleAdmin = payload => adminBattleAction(session.accessToken,snapshot.guild_id,payload)
  const imageAdmin = payload => uploadAdminImage(session.accessToken,snapshot.guild_id,payload)
  const settingsAdmin = settings => saveAdminSettings(session.accessToken,snapshot.guild_id,settings)
  const targets = () => loadCombatTargets(session.accessToken, snapshot.guild_id)
  const clash = payload => resolveActivityClash(session.accessToken, snapshot.guild_id, {...payload,channel_id:session.channelId})
  const encounters = channelId => loadEncounters(session.accessToken, snapshot.guild_id, channelId)
  const encounter = async payload => { const result = await encounterAction(session.accessToken, snapshot.guild_id, payload); if (result.result) await refresh(); return result }
  return <ActivityErrorBoundary><ActivityDataProvider snapshot={snapshot} auth={session.auth}><ThemeProvider themeId="theme-dossier-crimson"><Shell onProfileSaved={persistProfile} onStatusSaved={persistStatuses} onSkillSaved={persistSkill} onSkillDeleted={removeSkill} loadAdmin={admin} loadAdminEntityData={adminEntity} saveEntity={adminSave} saveAdminEntityData={adminSave} adminSkill={skillAdmin} enemyAction={enemyAdmin} battleAction={battleAdmin} imageAction={imageAdmin} loadTargets={targets} resolveClash={clash} loadEncounterData={encounters} runEncounterAction={encounter} /></ThemeProvider></ActivityDataProvider></ActivityErrorBoundary>
}
