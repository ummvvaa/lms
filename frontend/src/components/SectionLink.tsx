/**
 * Короткая сводка раздела на дашборде.
 *
 * Раздел живёт отдельным экраном, а на дашборде от него остаётся строка
 * с числом и ссылкой: «Группы — 12, открыть». Так дашборд не превращается
 * обратно в бесконечную ленту, но и не молчит о том, что в разделе есть.
 */
import { Link } from 'react-router-dom'
import { t } from '../i18n'

export default function SectionLink({
  title,
  value,
  note,
  to,
}: {
  title: string
  value: string | number
  note?: string
  to: string
}) {
  return (
    <Link className="card card-pad seclink" to={to}>
      <span className="seclink__body">
        <b className="seclink__title">{title}</b>
        {note && <span className="muted seclink__note">{note}</span>}
      </span>
      <span className="num seclink__value">{value}</span>
      <span className="seclink__go">{t('открыть')}</span>
    </Link>
  )
}
