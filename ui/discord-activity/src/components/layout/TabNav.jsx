import {
  Activity, BookOpen, Contact, Crosshair, History, Shield, Swords,
} from 'lucide-react'

// Abas técnicas (dados de jogo) e narrativas (registros de RP), como no
// painel de referência — mas sem nenhuma mecânica exclusiva copiada dele.
export const SHEET_TABS = [
  { id: 'overview', label: 'Visão Geral', icon: Activity, group: 'technical' },
  { id: 'identity', label: 'Identidade', icon: Contact, group: 'technical' },
  { id: 'attributes', label: 'Atributos', icon: Crosshair, group: 'technical' },
  { id: 'skills', label: 'Skills', icon: Swords, group: 'technical' },
  { id: 'passives', label: 'Passivas', icon: Shield, group: 'technical' },
  { id: 'records', label: 'Registros', icon: BookOpen, group: 'narrative' },
  { id: 'log', label: 'Histórico', icon: History, group: 'narrative' },
]

export function TabNav({ activeTab, onChange }) {
  const technical = SHEET_TABS.filter(t => t.group === 'technical')
  const narrative = SHEET_TABS.filter(t => t.group === 'narrative')
  return (
    <nav className="tab-nav">
      <span className="nav-label">TÉCNICO</span>
      {technical.map(tab => (
        <TabButton key={tab.id} tab={tab} active={activeTab === tab.id} onClick={() => onChange(tab.id)} />
      ))}
      <span className="nav-label">NARRATIVO</span>
      {narrative.map(tab => (
        <TabButton key={tab.id} tab={tab} active={activeTab === tab.id} onClick={() => onChange(tab.id)} />
      ))}
    </nav>
  )
}

function TabButton({ tab, active, onClick }) {
  const Icon = tab.icon
  return (
    <button className={active ? 'active' : ''} onClick={onClick}>
      <Icon />
      <span className="label-text">{tab.label}</span>
    </button>
  )
}
