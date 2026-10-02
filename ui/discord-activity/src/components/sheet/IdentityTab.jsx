// Identidade e descrição do personagem.
export function IdentityTab({ character }) {
  const { identity } = character
  return (
    <div className="identity-tab">
      <dl className="identity-facts">
        <div><dt>Nome</dt><dd>{identity.name || character.name || '—'}</dd></div>
        <div><dt>Idade</dt><dd>{identity.age || '—'}</dd></div>
        <div><dt>Altura & peso</dt><dd>{identity.height_weight || '—'}</dd></div>
        <div><dt>Gênero</dt><dd>{identity.gender || '—'}</dd></div>
        <div><dt>Sexualidade</dt><dd>{identity.sexuality || '—'}</dd></div>
        <div><dt>Association | Syndicate</dt><dd>{identity.affiliation || '—'}</dd></div>
        <div><dt>E.G.O.</dt><dd>{identity.ego || '—'}</dd></div>
      </dl>
      <section>
        <h3>Descrição</h3>
        <p>{identity.description}</p>
      </section>
      <section>
        <h3>Aparência</h3>
        <p>{identity.appearance}</p>
      </section>
    </div>
  )
}
