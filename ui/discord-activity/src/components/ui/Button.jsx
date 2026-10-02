// Botão base reaproveitado em toda a Activity (jogador e mestre).
// variant: 'solid' (ação principal) | 'ghost' (secundária) | 'danger'
export function Button({ variant = 'solid', icon: Icon, children, ...props }) {
  return (
    <button className={`ui-button variant-${variant}`} {...props}>
      {Icon && <Icon />}
      {children}
    </button>
  )
}
