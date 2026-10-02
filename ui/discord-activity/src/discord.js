import { DiscordSDK } from '@discord/embedded-app-sdk'

const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID
export let discordSdk = null
const withTimeout = (promise, message, milliseconds = 15000) => Promise.race([
  promise,
  new Promise((_, reject) => setTimeout(() => reject(new Error(message)), milliseconds)),
])
const apiPath = path => `/.proxy${path}`
const responseJson = async response => {
  const text = await response.text()
  try { return JSON.parse(text) }
  catch { throw new Error(`O servidor da Activity nao respondeu em JSON (${response.status}). Verifique se o App Launcher aponta para a URL publica atual.`) }
}
const fetchJson = async (path, options = {}) => {
  let response
  try {
    response = await fetch(apiPath(path), options)
  } catch {
    throw new Error('A Activity nao conseguiu falar com o servidor pelo proxy do Discord. Confirme a URL publica da Activity no Developer Portal.')
  }
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body
}
export async function checkActivityStatus() {
  return fetchJson('/api/activity/status')
}

export async function authenticateActivity() {
  if (!clientId) throw new Error('VITE_DISCORD_CLIENT_ID não configurado.')
  const status = await checkActivityStatus()
  if (!status.client_id_configured || !status.client_secret_configured) {
    throw new Error('Configure DISCORD_CLIENT_ID e DISCORD_CLIENT_SECRET no .env da Activity.')
  }
  if (!status.static_build) {
    throw new Error('Frontend da Activity ausente. Rode o build da Activity novamente.')
  }
  try {
    // O construtor exige os parâmetros internos que o Discord adiciona ao
    // iframe. Criá-lo no carregamento do módulo causava uma página branca
    // irrecuperável quando o link era aberto fora do App Launcher.
    discordSdk = new DiscordSDK(clientId)
  } catch {
    throw new Error('Abra o ClashBot pelo App Launcher dentro de um canal de voz do Discord.')
  }
  await withTimeout(discordSdk.ready(), 'O Discord não concluiu a abertura da Activity. Feche e abra pelo App Launcher.')
  const {code} = await withTimeout(discordSdk.commands.authorize({
    client_id: clientId,
    response_type: 'code',
    state: '',
    prompt: 'none',
    scope: ['identify', 'guilds'],
  }), 'O Discord não liberou a autorização da Activity.')
  const tokenBody = await fetchJson('/api/token', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code}),
  })
  if (!tokenBody.access_token) throw new Error('Falha ao autorizar com o Discord.')
  const auth = await withTimeout(discordSdk.commands.authenticate({access_token: tokenBody.access_token}), 'O Discord não confirmou a sessão da Activity.')
  if (!auth) throw new Error('O Discord não confirmou a sessão.')
  return {accessToken: tokenBody.access_token, auth, guildId: discordSdk.guildId || '', channelId: discordSdk.channelId || ''}
}

export async function loadOwnSheet(accessToken, guildId, signal) {
  const query = guildId ? `?guild_id=${encodeURIComponent(guildId)}` : ''
  const response = await fetch(apiPath(`/api/activity/me${query}`), {
    headers: {Authorization: `Bearer ${accessToken}`}, signal,
  })
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body
}

export async function saveOwnProfile(accessToken, guildId, profile) {
  const response = await fetch(apiPath('/api/activity/profile'), { method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}`}, body: JSON.stringify({guild_id: guildId, profile}) })
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body.profile
}
export async function saveOwnStatuses(accessToken,guildId,statuses) {
  const response=await fetch(apiPath('/api/activity/statuses/save'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({guild_id:guildId,statuses})});const body=await responseJson(response);if(!response.ok)throw new Error(body.error||`API ${response.status}`);return body
}

export async function saveOwnSkill(accessToken, guildId, skill) {
  const response = await fetch(apiPath('/api/activity/skills/save'), { method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${accessToken}`}, body:JSON.stringify({guild_id:guildId, skill}) })
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body
}

export async function deleteOwnSkill(accessToken, guildId, name) {
  const response = await fetch(apiPath('/api/activity/skills/delete'), { method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${accessToken}`}, body:JSON.stringify({guild_id:guildId, name}) })
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body
}

export async function loadAdminOverview(accessToken, guildId) {
  const response = await fetch(apiPath(`/api/activity/admin?guild_id=${encodeURIComponent(guildId)}`), {headers:{Authorization:`Bearer ${accessToken}`}})
  const body = await responseJson(response)
  if (!response.ok) throw new Error(body.error || `API ${response.status}`)
  return body
}

export async function loadCombatTargets(accessToken, guildId) {
  const response = await fetch(apiPath(`/api/activity/combat/targets?guild_id=${encodeURIComponent(guildId)}`), {headers:{Authorization:`Bearer ${accessToken}`}})
  const body = await responseJson(response); if (!response.ok) throw new Error(body.error || `API ${response.status}`); return body.targets
}

export async function resolveActivityClash(accessToken, guildId, payload) {
  const response = await fetch(apiPath('/api/activity/clash'), {method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})})
  const body = await responseJson(response); if (!response.ok) throw new Error(body.error || `API ${response.status}`); return body
}

export async function loadEncounters(accessToken, guildId, channelId='') {
  const channel = channelId ? `&channel_id=${encodeURIComponent(channelId)}` : ''
  const response = await fetch(apiPath(`/api/activity/encounters?guild_id=${encodeURIComponent(guildId)}${channel}`), {headers:{Authorization:`Bearer ${accessToken}`}})
  const body = await responseJson(response); if (!response.ok) throw new Error(body.error || `API ${response.status}`); return body
}

export async function encounterAction(accessToken, guildId, payload) {
  const response = await fetch(apiPath('/api/activity/encounter/action'), {method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})})
  const body = await responseJson(response); if (!response.ok) throw new Error(body.error || `API ${response.status}`); return body
}

export async function loadAdminEntity(accessToken,guildId,kind,ownerId) {
  const response=await fetch(apiPath(`/api/activity/admin/entity?guild_id=${encodeURIComponent(guildId)}&kind=${encodeURIComponent(kind)}&owner_id=${encodeURIComponent(ownerId)}`),{headers:{Authorization:`Bearer ${accessToken}`}}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function saveAdminEntity(accessToken,guildId,payload) {
  const response=await fetch(apiPath('/api/activity/admin/entity/save'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function uploadAdminImage(accessToken,guildId,payload) {
  const response=await fetch(apiPath('/api/activity/admin/image'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function adminSkillAction(accessToken,guildId,payload) {
  const response=await fetch(apiPath('/api/activity/admin/skill'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function adminEnemyAction(accessToken,guildId,payload) {
  const response=await fetch(apiPath('/api/activity/admin/enemy'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function adminBattleAction(accessToken,guildId,payload) {
  const response=await fetch(apiPath('/api/activity/admin/battle'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({...payload,guild_id:guildId})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
export async function saveAdminSettings(accessToken,guildId,settings) {
  const response=await fetch(apiPath('/api/activity/admin/settings'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${accessToken}`},body:JSON.stringify({guild_id:guildId,settings})}); const body=await responseJson(response); if(!response.ok)throw new Error(body.error||`API ${response.status}`); return body
}
