/**
 * «Сегодня кружок: AI Startup Lab, 15:00–18:00» на главной ученика — в день встречи
 * своего кружка. Нет встречи сегодня или пункта «Кружки» у параллели — ничего нет.
 */
import { useMyClubs } from '../../api/clubs'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows } from '../../components/patterns'
import { t } from '../../i18n'
import './clubs.css'

/** Есть ли у ученика встреча кружка сегодня — главная складывает пустое место. */
export function useTodayClubs() {
  const { me } = useAuth()
  const open = me?.role === 'student' && Boolean(me.sections?.includes('/clubs'))
  const { data } = useMyClubs(open)
  return open ? (data?.today ?? []) : []
}

export default function TodayClubs({ rows }: { rows: { id: number; title: string; time: string }[] }) {
  if (rows.length === 0) return null
  return (
    <section className="card card-pad">
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.id}
            // название — одной строкой, длинное режется многоточием, полное — в подсказке
            title={
              <span className="clubs-oneline" title={row.title}>
                {row.title}
              </span>
            }
            note={t('Сегодня кружок · {time}', { time: row.time })}
            to="/clubs"
          />
        ))}
      </Rows>
    </section>
  )
}
