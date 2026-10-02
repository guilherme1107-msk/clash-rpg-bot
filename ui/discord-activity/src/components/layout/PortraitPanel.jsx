// Retrato estático da ficha, com um "estado" visual opcional
// (normal | wounded | altered) — sem troca de sprite por aba.
export function PortraitPanel({ character }) {
  return (
    <aside className="portrait-panel">
      {character.portraitState !== 'normal' && (
        <span className="state-tag">
          {character.portraitState === 'wounded' ? 'FERIDO' : 'ESTADO ALTERADO'}
        </span>
      )}
      <div className={`portrait-frame state-${character.portraitState}`}>
        <img src={character.portrait} alt={`Retrato de ${character.name}`} />
      </div>
      <div className="portrait-identity">
        <p className="eyebrow">IDENTIDADE // FICHA</p>
        <h2>{character.name}</h2>
        <p className="title">{character.title}</p>
        <blockquote>&ldquo;{character.quote}&rdquo;</blockquote>
      </div>
    </aside>
  )
}
