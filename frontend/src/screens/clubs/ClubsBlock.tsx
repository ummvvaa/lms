/**
 * Блок «Кружки» в карточке ученика у куратора (31.10.2026): в каких кружках,
 * с какой даты, вышел ли. Только чтение — записывается ученик сам. Заметок
 * ментора здесь нет; посещение — только если в кружке включена отметка.
 */
import { useStudentClubs } from '../../api/clubs'
import { Chip, DataCard, ErrorNote, Loading } from '../../components/ui'
import { t } from '../../i18n'
import { formatDayMonth } from '../../lib/format'
import '../directors/directors.css'

export default function ClubsBlock({ studentId }: { studentId: number }) {
  const { data, isLoading, error } = useStudentClubs(studentId)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (data.rows.length === 0)
    return <DataCard title={t('Кружки')} empty={t('ни в одном кружке · записывается ученик сам')} />
  return (
    <DataCard title={t('Кружки')} note={t('Только просмотр · записывается ученик сам')}>
      <div className="dir__rows">
        {data.rows.map((row) => (
          <div key={row.id} className="dir__row">
            <span className="dir__what">
              <b>{row.club}</b>
              <span className="t-note">
                {[
                  row.schedule,
                  t('с {date}', { date: formatDayMonth(row.enrolled_at) }),
                  row.left && row.ended_at ? t('вышел {date}', { date: formatDayMonth(row.ended_at) }) : '',
                  // посещение — только при включённой отметке
                  row.percent === undefined
                    ? ''
                    : row.percent === null
                      ? t('встреч в этом месяце не было')
                      : t('посещение за месяц {n}%', { n: row.percent }),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
            {row.left ? (
              <Chip size="sm">{t('вышел')}</Chip>
            ) : (
              <Chip tone="good" size="sm">
                {t('в кружке')}
              </Chip>
            )}
          </div>
        ))}
      </div>
    </DataCard>
  )
}
