import { useActivityData } from '../activityData'

// Simula a detecção de papel do "usuário logado" — sem autenticação Discord
// real ainda. Quando o backend/OAuth existir, troque o corpo desta função
// por algo que leia o usuário autenticado de verdade; o formato de retorno
// pode continuar o mesmo para não quebrar quem consome o hook.
export function useRole() {
  return useActivityData().role
}
