import { useEffect, useRef, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { UPTIE_COSTS, UPTIE_UNLOCKS } from '../../progression'

const numerals = ['I', 'II', 'III', 'IV', 'V']

export function UptieDisplay({ current = 1 }) {
  const [open, setOpen] = useState(false)
  const [ceremony, setCeremony] = useState(false)
  const stage = Math.max(1, Math.min(5, Number(current)))
  const previous = useRef(stage)
  useEffect(() => {
    if (stage > previous.current) setCeremony(true)
    previous.current = stage
  }, [stage])
  return <section className="uptie-display">
    {ceremony && <div className={`uptie-ceremony stage-${stage}`} onAnimationEnd={() => setCeremony(false)}><div className="ceremony-scene"><i className="ceremony-ring"/><i className="ceremony-ring ring-two"/><i className="ceremony-sigil">✦</i><i className="ceremony-chain left">⛓</i><i className="ceremony-chain right">⛓</i><i className="ceremony-shard shard-one"/><i className="ceremony-shard shard-two"/><i className="ceremony-shard shard-three"/></div><div className="ceremony-copy"><span>IDENTITY SYNCHRONIZATION</span><strong>{numerals[stage - 1]}</strong><h2>UPTIE</h2><p>{stage === 1 ? 'IDENTIDADE INICIAL' : stage === 2 ? 'REFINAMENTO DE EGO' : stage === 3 ? 'LIMITADORES EM RUPTURA' : stage === 4 ? 'MANIFESTAÇÃO CONFIRMADA' : 'SINGULARIDADE DESPERTA'}</p></div></div>}
    <button className="uptie-emblem" onClick={() => setOpen(value => !value)} aria-expanded={open}><span>UPTIE</span><strong>{numerals[stage - 1]}</strong><i>{open ? 'RECOLHER' : 'DETALHES'}</i></button>
    <div className="uptie-overview"><div className="uptie-stages">{numerals.map((label, index) => <i className={index + 1 === stage ? 'current' : index + 1 < stage ? 'complete' : ''} key={label}><b>{label}</b><small>{index + 1 === stage ? 'ATUAL' : index + 1 < stage ? 'ATIVO' : 'BLOQUEADO'}</small></i>)}</div>{open && <div className="uptie-details"><header><div><span>ESTÁGIO DE SINCRONIZAÇÃO</span><h3>Uptie {numerals[stage - 1]}</h3></div><b>{UPTIE_COSTS[stage - 1] ? `${UPTIE_COSTS[stage - 1]} Thread` : 'Inicial'}</b></header><ul>{UPTIE_UNLOCKS[stage - 1].map(item => <li key={item}>{item}</li>)}</ul><button onClick={() => setCeremony(true)}><Sparkles/> Ver cerimônia</button></div>}</div>
  </section>
}
