import { useState } from 'react'
import { HeartCrack, Minus, Plus } from 'lucide-react'
import { CombatMeter } from '../ui/CombatMeter'
import { Button } from '../ui/Button'
import { UptieDisplay } from './UptieDisplay'
import { StatusTab } from './StatusTab'
import { DamageModal } from './DamageModal'

// Visão geral: HP, SP, Stagger, Light, Offense e Defense.
export function OverviewTab({ character, onSave, onStatusSave }) {
  const identity = character.identity || {}
  const [damageOpen,setDamageOpen]=useState(false), [savingLight,setSavingLight]=useState(false), [error,setError]=useState('')
  const thresholds=character.profile?.stagger_thresholds||[Math.round(character.hp.maximum*.2),Math.round(character.hp.maximum*.5)]
  const changeLight=async delta=>{if(savingLight||!onSave)return;const light=Math.max(0,Math.min(character.light.maximum,character.light.current+delta));if(light===character.light.current)return;setSavingLight(true);setError('');try{await onSave({...character.profile,light})}catch(cause){setError(cause.message||'Não foi possível alterar o Light.')}finally{setSavingLight(false)}}
  return (
    <div className="overview-tab">
      {onSave&&<section className="quick-resources"><Button variant="ghost" icon={HeartCrack} onClick={()=>setDamageOpen(true)}>Receber dano</Button><div className="light-stepper"><span>LIGHT</span><button type="button" title="Diminuir Light" disabled={savingLight||character.light.current<=0} onClick={()=>changeLight(-1)}><Minus/></button><strong>{character.light.current} / {character.light.maximum}</strong><button type="button" title="Aumentar Light" disabled={savingLight||character.light.current>=character.light.maximum} onClick={()=>changeLight(1)}><Plus/></button></div></section>}
      {error&&<p className="edit-error">{error}</p>}
      <div className="overview-meters">
        <CombatMeter label="HP" tone="hp" current={character.hp.current} maximum={character.hp.maximum} />
        <CombatMeter label="SP" tone="sp" current={character.sp.current} maximum={character.sp.maximum} />
        <CombatMeter label="LIGHT" tone="light" current={character.light.current} maximum={character.light.maximum} />
      </div>
      <section className="stagger-thresholds"><header><span>STAGGER THRESHOLDS</span><small>Limites calculados pela Vida Máxima</small></header>{thresholds.map((value,index)=><div key={index}><span>STAGGER {index?'II':'I'} <i>{index?'50%':'20%'}</i></span><b>{value} HP</b><div><em style={{width:`${index?50:20}%`}}/></div></div>)}</section>
      <div className="overview-stats">
        <div className="stat-card">
          <span>OFFENSE</span>
          <strong>{character.offense}</strong>
        </div>
        <div className="stat-card">
          <span>DEFENSE</span>
          <strong>{character.defense}</strong>
        </div>
        <UptieDisplay current={character.uptie || 1} />
      </div>
      <section className="overview-identity">
        <header><span>IDENTIFICAÇÃO</span><small>NÍVEL {character.level}</small></header>
        <dl>
          <div><dt>Nome</dt><dd>{identity.name || character.name}</dd></div>
          <div><dt>Idade</dt><dd>{identity.age || '—'}</dd></div>
          <div><dt>Altura / Peso</dt><dd>{identity.height_weight || '—'}</dd></div>
          <div><dt>Gênero</dt><dd>{identity.gender || '—'}</dd></div>
          <div><dt>Association</dt><dd>{identity.affiliation || '—'}</dd></div>
          <div><dt>E.G.O.</dt><dd>{identity.ego || '—'}</dd></div>
        </dl>
      </section>
      <StatusTab character={character} statuses={character.statuses || []} onSave={onStatusSave} />
      <DamageModal character={character} open={damageOpen} onClose={()=>setDamageOpen(false)} onSave={onSave}/>
    </div>
  )
}
