import { ShieldHalf, User } from 'lucide-react'
import { useActivityData } from '../../activityData'

export function Topbar({ role, actions }) {
  const { character } = useActivityData()
  return (
    <header className="topbar">
      <div className="brand-mark"><span>C</span></div>
      <div className="brand-copy">
        <p>CLASHBOT // FICHA DE CAMPO</p>
        <h1>{character?.name || 'Ficha'}</h1>
      </div>
      <div className="topbar-actions">
        {actions}
        <span className={`role-badge ${role.isMaster ? 'master' : ''}`}>
          {role.isMaster ? <ShieldHalf /> : <User />}
          {role.isMaster ? 'Mestre' : role.isOwner ? 'Jogador (dono)' : 'Jogador'}
        </span>
      </div>
    </header>
  )
}
