import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { useActivityData } from '../../activityData'
import { useRole } from '../../hooks/useRole'
import { PortraitPanel } from '../layout/PortraitPanel'
import { TabNav } from '../layout/TabNav'
import { Button } from '../ui/Button'
import { OverviewTab } from './OverviewTab'
import { IdentityTab } from './IdentityTab'
import { AttributesTab } from './AttributesTab'
import { SkillsTab } from './SkillsTab'
import { PassivesTab } from './PassivesTab'
import { RecordsTab } from './RecordsTab'
import { SheetEditModal } from './SheetEditModal'
import { CombatLog } from '../combat/CombatLog'

// Tela da ficha do jogador: retrato + console com abas.
export function SheetScreen({ bare = false, onProfileSaved, onStatusSaved, onSkillSaved, onSkillDeleted }) {
  const [tab, setTab] = useState('overview')
  const [editOpen, setEditOpen] = useState(false)
  const { character, combatLog } = useActivityData()
  const role = useRole()
  const editorLabel = { overview: 'Editar recursos', identity: 'Editar identidade', attributes: 'Editar nível e perícias' }[tab]

  const renderTab = () => {
    switch (tab) {
      case 'overview': return <OverviewTab character={character} onSave={onProfileSaved} onStatusSave={onStatusSaved} />
      case 'identity': return <IdentityTab character={character} />
      case 'attributes': return <AttributesTab character={character} />
      case 'skills': return <SkillsTab skills={character.skills} onSave={onSkillSaved} onDelete={onSkillDeleted} />
      case 'passives': return <PassivesTab passives={character.passives} character={character} onSave={onProfileSaved} />
      case 'records': return <RecordsTab character={character} onSave={onProfileSaved} />
      case 'log': return <CombatLog entries={combatLog} />
      default: return null
    }
  }

  const console = (
    <section className="console-panel">
      {role.canEditSheet && editorLabel && (
        <div className="console-toolbar">
          <Button variant="ghost" icon={Pencil} onClick={() => setEditOpen(true)}>{editorLabel}</Button>
        </div>
      )}
      <TabNav activeTab={tab} onChange={setTab} />
      <div className="tab-content">{renderTab()}</div>
      <SheetEditModal character={character} section={tab} open={editOpen} onClose={() => setEditOpen(false)} onSave={async profile => { await onProfileSaved?.(profile); setEditOpen(false) }} />
    </section>
  )

  if (bare) return console
  return (
    <div className="sheet-layout">
      <PortraitPanel character={character} />
      {console}
    </div>
  )
}
