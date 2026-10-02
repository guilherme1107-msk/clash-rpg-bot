import { useEffect, useState } from 'react'
import { HeartCrack } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'

export function DamageModal({ character, open, onClose, onSave }) {
  const [damage,setDamage] = useState(''), [saving,setSaving] = useState(false), [error,setError] = useState('')
  useEffect(()=>{if(open){setDamage('');setError('')}},[open])
  if(!open)return null
  const amount=Math.max(0,Math.floor(Number(damage)||0))
  const hpAfter=Math.max(0,character.hp.current-amount)
  const apply=async()=>{if(!amount)return;setSaving(true);setError('');try{await onSave?.({...character.profile,hp:hpAfter});onClose?.()}catch(cause){setError(cause.message||'Não foi possível aplicar o dano.')}finally{setSaving(false)}}
  return <Modal title="Dano recebido" eyebrow="CONTROLE RÁPIDO" open={open} onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="solid" icon={HeartCrack} disabled={!amount||saving} onClick={apply}>{saving?'Aplicando…':'Aplicar dano'}</Button></>}>
    <section className="damage-dialog"><div><span>HP ATUAL</span><strong>{character.hp.current}<i>/</i>{character.hp.maximum}</strong></div><label>Quanto dano foi recebido?<input autoFocus type="number" min="1" value={damage} placeholder="Digite o dano" onChange={event=>setDamage(event.target.value)} onKeyDown={event=>event.key==='Enter'&&apply()}/></label><div><span>HP DEPOIS</span><strong>{hpAfter}<i>/</i>{character.hp.maximum}</strong></div></section>
    {error&&<p className="edit-error">{error}</p>}
  </Modal>
}
