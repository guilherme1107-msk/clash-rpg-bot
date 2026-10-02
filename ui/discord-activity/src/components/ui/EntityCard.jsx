// Card base compartilhado por skills, passivas e status — cada um usa uma
// variante (type) que decide quais campos extras aparecer.
// type: 'skill' | 'passive' | 'status'
export function EntityCard({ type = 'skill', title, eyebrow, active, kind, children }) {
  return (
    <article className={`entity-card type-${type} ${active ? 'is-active' : ''} ${kind ? `kind-${kind}` : ''}`}>
      <div className="entity-card-head">
        {eyebrow && <span>{eyebrow}</span>}
        {active && <em>ATIVA</em>}
      </div>
      <h3>{title}</h3>
      <div className="entity-card-body">{children}</div>
    </article>
  )
}
