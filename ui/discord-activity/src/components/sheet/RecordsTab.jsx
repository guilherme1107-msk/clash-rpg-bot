import { useState } from 'react'
import { Backpack, Heart, NotebookPen, Plus, ScrollText, Trash2 } from 'lucide-react'

const SECTIONS = [{ id:'inventory', label:'Inventário', icon:Backpack, fields:['Item','Quantidade','Detalhes'] }, { id:'notes', label:'Notas', icon:NotebookPen, fields:['Título','Conteúdo'] }, { id:'relationships', label:'Relações', icon:Heart, fields:['Nome','Vínculo','Detalhes'] }, { id:'memories', label:'Memórias', icon:ScrollText, fields:['Título','Descrição'] }]
const asObject = (item, index) => typeof item === 'string' ? { id:`old-${index}`, title:item, body:item, name:item, quantity:1 } : item

export function RecordsTab({ character, onSave }) {
  const [section, setSection] = useState('inventory')
  const [fields, setFields] = useState(['', '', ''])
  const config = SECTIONS.find(item => item.id === section)
  const entries = (character[section] || []).map(asObject)
  const update = async next => onSave?.({ ...character.profile, records: { ...(character.profile?.records || {}), [section]: next } })
  const setValue = (index, value) => setFields(current => current.map((old, i) => i === index ? value : old))
  const add = async event => { event.preventDefault(); if (!fields[0]?.trim()) return; const entry = section === 'inventory' ? { id:crypto.randomUUID(), name:fields[0], quantity:Number(fields[1] || 1), notes:fields[2] } : section === 'relationships' ? { id:crypto.randomUUID(), name:fields[0], bond:fields[1], notes:fields[2] } : { id:crypto.randomUUID(), title:fields[0], body:fields[1] }; await update([...entries, entry]); setFields(['','','']) }
  const remove = id => update(entries.filter(item => item.id !== id))
  return <div className="records-tab"><div className="records-subnav">{SECTIONS.map(item => { const Icon=item.icon; return <button key={item.id} className={section === item.id ? 'active' : ''} onClick={() => { setSection(item.id); setFields(['','','']) }}><Icon />{item.label}</button> })}</div><div className="records-body"><ul className="record-list">{entries.map(item => <li key={item.id}><button className="record-delete" title="Remover" onClick={() => remove(item.id)}><Trash2 /></button>{section === 'inventory' && <div><strong>{item.name}</strong><span>x{item.quantity}</span></div>}{section === 'relationships' && <div><strong>{item.name}</strong><span>{item.bond}</span></div>}{(section === 'notes' || section === 'memories') && <strong>{item.title}</strong>}{(item.notes || item.body) && <p>{item.notes || item.body}</p>}</li>)}</ul><form className="record-composer" onSubmit={add}><header><Plus /><div><span>ADICIONAR EM {config.label.toUpperCase()}</span><small>Salva direto na ficha.</small></div></header><div className="record-fields">{config.fields.map((label,index) => <label key={label}><span>{label}</span>{(label === 'Detalhes' || label === 'Conteúdo' || label === 'Descrição') ? <textarea value={fields[index] || ''} onChange={e => setValue(index, e.target.value)} /> : <input value={fields[index] || ''} onChange={e => setValue(index, e.target.value)} type={label === 'Quantidade' ? 'number' : 'text'} min="1" />}</label>)}</div><button type="submit">+ Adicionar</button></form></div></div>
}
