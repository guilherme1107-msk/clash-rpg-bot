import { useEffect, useState } from 'react'

// Roteador minimalista baseado em hash (#/combat, #/master), sem depender
// de bibliotecas externas — funciona bem dentro do iframe da Discord Activity
// porque não exige nenhuma configuração de servidor para as rotas.
export function useHashRoute() {
  const read = () => window.location.hash.replace(/^#/, '') || '/'
  const [route, setRoute] = useState(read)

  useEffect(() => {
    const onHashChange = () => setRoute(read())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const navigate = path => { window.location.hash = path }

  return { route, navigate }
}
