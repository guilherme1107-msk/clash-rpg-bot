// Campos de formulário base — usados no modal de edição e nos painéis de mestre.
export function TextField({ label, ...props }) {
  return (
    <label className="ui-field">
      {label && <span>{label}</span>}
      <input {...props} />
    </label>
  )
}

export function TextAreaField({ label, ...props }) {
  return (
    <label className="ui-field">
      {label && <span>{label}</span>}
      <textarea {...props} />
    </label>
  )
}

export function NumberField({ label, ...props }) {
  return (
    <label className="ui-field ui-field-number">
      {label && <span>{label}</span>}
      <input type="number" {...props} />
    </label>
  )
}
