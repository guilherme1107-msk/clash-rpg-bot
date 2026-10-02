import { createContext, useContext, useMemo } from 'react'
import { themesMock } from '../mockData'

// Aplica um tema completo (cores, fontes, textura) como CSS custom
// properties na raiz do componente. Cada personagem pode ter o seu.
const ThemeContext = createContext(themesMock['theme-dossier-crimson'])

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeProvider({ themeId, children }) {
  const theme = themesMock[themeId] || themesMock['theme-dossier-crimson']

  const cssVars = useMemo(() => {
    const c = theme.colors
    return {
      '--font-display': theme.fontDisplay,
      '--font-body': theme.fontBody,
      '--color-bg': c.bg,
      '--color-bg-panel': c.bgPanel,
      '--color-bg-console': c.bgConsole,
      '--color-border': c.border,
      '--color-border-strong': c.borderStrong,
      '--color-accent': c.accent,
      '--color-accent-strong': c.accentStrong,
      '--color-text-main': c.textMain,
      '--color-text-dim': c.textDim,
      '--color-text-faint': c.textFaint,
    }
  }, [theme])

  return (
    <ThemeContext.Provider value={theme}>
      <div className={`theme-root texture-${theme.texture}`} style={cssVars}>
        {children}
      </div>
    </ThemeContext.Provider>
  )
}
