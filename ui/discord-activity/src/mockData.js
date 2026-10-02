// =============================================================
// mockData.js
// -------------------------------------------------------------
// ÚNICO arquivo com todos os dados falsos da Activity.
// Nomes de campos em inglês (para bater com o futuro backend),
// textos exibidos na interface em português.
//
// Quando o backend real existir, cada export aqui vira uma
// chamada de API/hook que devolve objetos no MESMO formato.
// =============================================================

// -------------------------------------------------------------
// "Usuário logado" — simula quem está vendo a Activity.
// Não há autenticação Discord real aqui: troque este ID para
// testar os diferentes papéis (jogador dono / outro jogador / mestre).
// -------------------------------------------------------------
export const CURRENT_USER_ID = 'user-player-01'

export const usersMock = [
  { id: 'user-player-01', displayName: 'Theo', role: 'player', ownsCharacterId: 'char-001' },
  { id: 'user-player-02', displayName: 'Ana', role: 'player', ownsCharacterId: 'char-002' },
  { id: 'user-master-01', displayName: 'Mestre Iuri', role: 'master', ownsCharacterId: null },
]

// -------------------------------------------------------------
// Tema visual por personagem — cor, fontes e textura de fundo.
// Tudo isso vira CSS custom properties via ThemeProvider.
// -------------------------------------------------------------
export const themesMock = {
  'theme-dossier-crimson': {
    id: 'theme-dossier-crimson',
    label: 'Dossiê Escarlate',
    fontDisplay: "'Cormorant Garamond', serif",
    fontBody: "'IBM Plex Mono', monospace",
    colors: {
      bg: '#09090a',
      bgPanel: '#121011',
      bgConsole: '#0e0d0e',
      border: '#3e3332',
      borderStrong: '#5e3034',
      accent: '#bd2634',
      accentStrong: '#d92b3b',
      textMain: '#e8e0d7',
      textDim: '#8d7d75',
      textFaint: '#5e4d4c',
    },
    texture: 'grain',
  },
  'theme-ashen-void': {
    id: 'theme-ashen-void',
    label: 'Cinzas do Vazio',
    fontDisplay: "'Cormorant Garamond', serif",
    fontBody: "'IBM Plex Mono', monospace",
    colors: {
      bg: '#0a0b0d',
      bgPanel: '#111318',
      bgConsole: '#0d0f13',
      border: '#2b3038',
      borderStrong: '#39424f',
      accent: '#5b8ac9',
      accentStrong: '#7fb2f2',
      textMain: '#dbe4ee',
      textDim: '#7c8794',
      textFaint: '#4a525c',
    },
    texture: 'grain',
  },
}

// -------------------------------------------------------------
// Ficha de personagem — todos os grupos de campos.
// -------------------------------------------------------------
export const characterMock = {
  id: 'char-001',
  ownerId: 'user-player-01',
  themeId: 'theme-dossier-crimson',

  // ---- visão geral ----
  portrait: '/portraits/character-placeholder.svg',
  portraitState: 'normal', // normal | wounded | altered
  name: 'Kaelen Duskwright',
  title: 'O Errante das Backstreets',
  quote: 'Cada dívida se paga. Inclusive as minhas.',

  hp: { current: 62, maximum: 90 },
  sp: { current: 8, maximum: 12 },
  stagger: { current: 30, maximum: 45 },
  light: { current: 2, maximum: 4 },
  offense: 27,
  defense: 22,

  // ---- identidade e descrição ----
  identity: {
    age: '27 anos (aparente)',
    origin: 'Backstreets, Distrito Baixo',
    affiliation: 'Independente',
    description:
      'Um homem de fala curta e passos silenciosos. Carrega mais cicatrizes do que memórias que admite ter.',
    appearance:
      'Casaco surrado cor de ferrugem, luvas remendadas, uma cicatriz fina cruzando a sobrancelha esquerda.',
  },

  // ---- atributos, perícias, resistências ----
  attributes: [
    { name: 'Força', value: 14 },
    { name: 'Destreza', value: 17 },
    { name: 'Constituição', value: 13 },
    { name: 'Inteligência', value: 11 },
    { name: 'Sabedoria', value: 12 },
    { name: 'Carisma', value: 9 },
  ],
  proficiencies: [
    { name: 'Furtividade', value: 6 },
    { name: 'Luta', value: 5 },
    { name: 'Percepção', value: 3 },
    { name: 'Investigação', value: 2 },
    { name: 'Sobrevivência', value: 4 },
    { name: 'Intimidação', value: 1 },
  ],
  resistances: [
    { name: 'Corte', tier: 'resistente', icon: 'sword' },
    { name: 'Fogo', tier: 'normal', icon: 'flame' },
    { name: 'Veneno', tier: 'fraco', icon: 'flask' },
    { name: 'Sangramento', tier: 'imune', icon: 'droplet' },
    { name: 'Perfuração', tier: 'normal', icon: 'target' },
    { name: 'Contusão', tier: 'resistente', icon: 'shield' },
  ],

  // ---- status ativos (Potency e Count) ----
  statuses: [
    {
      id: 'status-01',
      name: 'Sangramento',
      potency: 4,
      count: 3,
      kind: 'negative',
      description: 'Perde HP igual à Potency no início do turno. Reduz 1 Count por rodada.',
    },
    {
      id: 'status-02',
      name: 'Foco de Combate',
      potency: 2,
      count: 2,
      kind: 'positive',
      description: '+Potency em rolagens de dano com armas cortantes.',
    },
  ],

  // ---- skills ----
  skills: [
    {
      id: 'skill-01',
      slot: 'Skill 1',
      name: 'Corte Sombrio',
      basePower: 14,
      coinPower: 3,
      coins: 2,
      coinTypes: { positive: 1, negative: 1, unbreakable: 0 },
      damageType: 'Corte',
      description: 'Um golpe rápido vindo das sombras, difícil de antecipar.',
      effects: ['Em acerto crítico, aplica 2 de Sangramento (Count 2).'],
    },
    {
      id: 'skill-02',
      slot: 'Skill 2',
      name: 'Investida Baixa',
      basePower: 11,
      coinPower: 2,
      coins: 3,
      coinTypes: { positive: 1, negative: 1, unbreakable: 1 },
      damageType: 'Contusão',
      description: 'Avança sob a guarda do alvo, sacrificando precisão por impacto.',
      effects: ['Se todas as moedas vencerem, ignora metade da Defesa do alvo.'],
    },
    {
      id: 'skill-03',
      slot: 'Skill 3',
      name: 'Retalho Final',
      basePower: 18,
      coinPower: 4,
      coins: 2,
      coinTypes: { positive: 0, negative: 2, unbreakable: 0 },
      damageType: 'Corte',
      description: 'Um golpe arriscado, mais forte quanto mais ferido ele estiver.',
      effects: ['+1 Base Power para cada 20% de HP perdido.'],
    },
  ],

  // ---- passivas ----
  passives: [
    {
      id: 'passive-01',
      name: 'Reflexos de Beco',
      category: 'combat',
      trigger: 'Ao ser alvo de um ataque surpresa',
      description: '+2 de Destreza para testes de esquiva neste turno.',
      active: true,
    },
    {
      id: 'passive-02',
      name: 'Memória Muda',
      category: 'roleplay',
      trigger: 'Sempre ativa',
      description: 'Nunca revela voluntariamente detalhes do próprio passado.',
      active: true,
    },
  ],

  // ---- registros narrativos ----
  inventory: [
    { id: 'item-01', name: 'Adaga enferrujada', quantity: 1, notes: 'Pertenceu a alguém que ele não nomeia.' },
    { id: 'item-02', name: 'Kit de primeiros socorros', quantity: 2, notes: '' },
    { id: 'item-03', name: 'Moedas fora de circulação', quantity: 14, notes: 'Guardadas, nunca gastas.' },
  ],
  notes: [
    { id: 'note-01', title: 'Sobre o contato do Distrito Baixo', body: 'Ele sabe mais do que finge saber. Cuidado.' },
  ],
  relationships: [
    { id: 'rel-01', name: 'Mestre Iuri (NPC: "A Corretora")', bond: 'Desconfiança mútua', notes: 'Negócios, nunca amizade.' },
  ],
  memories: [
    { id: 'mem-01', title: 'A última dívida', body: 'Uma lembrança que ele guarda e não compartilha com ninguém.' },
  ],
}

// -------------------------------------------------------------
// Combate — alvos, estado de clash, ataque livre e histórico.
// -------------------------------------------------------------
export const combatTargetsMock = [
  { id: 'target-enemy-01', name: 'Batedor das Sombras', hp: { current: 18, maximum: 40 }, kind: 'enemy' },
  { id: 'target-enemy-02', name: 'Guarda Corrompido', hp: { current: 55, maximum: 55 }, kind: 'enemy' },
  { id: 'target-ally-01', name: 'Ana (Aliada)', hp: { current: 30, maximum: 50 }, kind: 'ally' },
]

export const combatLogMock = [
  { id: 'log-01', turn: 3, timestamp: '00:41', kind: 'clash', text: 'Kaelen venceu o Clash contra Batedor das Sombras (14 x 9).' },
  { id: 'log-02', turn: 3, timestamp: '00:39', kind: 'damage', text: 'Batedor das Sombras recebeu 12 de dano (Corte).' },
  { id: 'log-03', turn: 2, timestamp: '00:22', kind: 'status', text: 'Kaelen aplicou Sangramento (Potency 4, Count 3) em Batedor das Sombras.' },
  { id: 'log-04', turn: 2, timestamp: '00:15', kind: 'system', text: 'Início da Rodada 2.' },
  { id: 'log-05', turn: 1, timestamp: '00:03', kind: 'attack', text: 'Kaelen usou Corte Sombrio em Batedor das Sombras.' },
]

// -------------------------------------------------------------
// Área de mestre — inimigos e controle de batalha.
// -------------------------------------------------------------
export const enemiesMock = [
  {
    id: 'enemy-01',
    name: 'Batedor das Sombras',
    portrait: '/portraits/enemy-placeholder.svg',
    hp: { current: 18, maximum: 40 },
    stagger: { current: 5, maximum: 20 },
    offense: 16,
    defense: 10,
    initiative: 14,
    statuses: [{ id: 'st-e01', name: 'Sangramento', potency: 4, count: 2, kind: 'negative' }],
  },
  {
    id: 'enemy-02',
    name: 'Guarda Corrompido',
    portrait: '/portraits/enemy-placeholder.svg',
    hp: { current: 55, maximum: 55 },
    stagger: { current: 25, maximum: 25 },
    offense: 20,
    defense: 18,
    initiative: 9,
    statuses: [],
  },
]

export const battleStateMock = {
  round: 3,
  turnOrder: ['char-001', 'enemy-01', 'user-player-02', 'enemy-02'],
  currentTurnId: 'enemy-01',
}
