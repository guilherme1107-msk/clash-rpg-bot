import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles/base.css'
import './styles/layout.css'
import './styles/ui.css'
import './styles/sheet.css'
import './styles/combat.css'
import './styles/master.css'
import './styles/dossier.css'
import './styles/encounter-overview.css'
import './styles/encounter.css'

// OAuth authorization codes are single-use; StrictMode replays effects.
createRoot(document.getElementById('root')).render(<App />)
