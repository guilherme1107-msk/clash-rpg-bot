import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { EntityCard } from '../ui/EntityCard'

export function PassivesTab({ passives = [], character, onSave }) {
  const [draft, setDraft] = useState({ name:'', trigger:'', description:'', category:'combat' })
  const add = async event => { event.preventDefault(); if (!draft.name.trim()) return; await onSave?.({ ...character.profile, passives:[...passives, { ...draft, id:crypto.randomUUID(), active:true }] }); setDraft({ name:'', trigger:'', description:'', category:'combat' }) }
  const remove = id => onSave?.({ ...character.profile, passives:passives.filter(item => item.id !== id) })
  return <div className="passives-tab"><div className="cards-grid">{passives.map(passive => <EntityCard key={passive.id} type="passive" active={passive.active} eyebrow={passive.category === 'roleplay' ? 'NARRATIVA' : 'COMBATE'} title={passive.name}><button className="record-delete" onClick={() => remove(passive.id)}><Trash2 /></button><p className="passive-trigger">{passive.trigger}</p><p>{passive.description}</p></EntityCard>)}</div><form className="passive-composer" onSubmit={add}><header><Plus /><div><span>NOVA PASSIVA</span><small>Uma passiva entra vinculada à sua ficha.</small></div></header><div className="record-fields"><label><span>Nome</span><input value={draft.name} onChange={e => setDraft({...draft,name:e.target.value})}/></label><label><span>Categoria</span><select value={draft.category} onChange={e => setDraft({...draft,category:e.target.value})}><option value="combat">Combate</option><option value="roleplay">Narrativa</option></select></label><label><span>Gatilho</span><input value={draft.trigger} onChange={e => setDraft({...draft,trigger:e.target.value})}/></label><label><span>Descrição</span><textarea value={draft.description} onChange={e => setDraft({...draft,description:e.target.value})}/></label></div><button type="submit">+ Registrar passiva</button></form></div>
}
