/** Заглушка под будущий экран. Наполняется в Фазах 3–6. */
interface Props {
  emoji: string
  title: string
  note: string
}

export default function Placeholder({ emoji, title, note }: Props) {
  return (
    <div>
      <span className="eyebrow">
        {emoji} {title}
      </span>
      <h1 className="screen__title">{title}</h1>
      <div className="card card-pad screen__empty">
        <p className="muted">{note}</p>
      </div>
    </div>
  )
}
