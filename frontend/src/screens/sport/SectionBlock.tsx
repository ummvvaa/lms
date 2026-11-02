/**
 * Блок «Секции» в карточке ученика у куратора (макет CStudents, 27.10.2026):
 * по каждой секции ученика — где и когда занимается, посещение за месяц,
 * последние отметки. Только чтение — записывает и переводит директор спорта.
 */
import { useStudentSection } from '../../api/sport'
import { Chip, DataCard, ErrorNote, Loading } from '../../components/ui'
import { t } from '../../i18n'
import { formatDateLong, formatWeekday } from '../../lib/format'
import '../directors/directors.css'
import './sport.css'

export default function SectionBlock({ studentId }: { studentId: number }) {
  const { data, isLoading, error } = useStudentSection(studentId)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (!data.enrolled)
    return (
      <DataCard
        title={t('Секции')}
        empty={t('не записан ни в одну секцию · записать может директор спорта')}
      />
    )
  return (
    <DataCard
      title={t('Секции')}
      count={data.rows.length}
      note={t('Только просмотр · записывает и переводит директор спорта')}
    >
      {data.rows.map((row) => (
        <div key={row.id} className="sport-block">
          <div className="dir__lines">
            <div className="dir__line">
              <span>{row.section}</span>
              <b>{row.slot || t('час не выбран')}</b>
            </div>
            <div className="dir__line">
              <span>{t('Адрес')}</span>
              <b>{row.address}</b>
            </div>
            <div className="dir__line">
              <span>{t('Посещение за месяц')}</span>
              {row.percent === null ? (
                <b>{t('занятий не было')}</b>
              ) : row.below ? (
                <Chip tone="warn" size="sm" className="num">{`${row.percent}%`}</Chip>
              ) : (
                <b className="num">{row.percent}%</b>
              )}
            </div>
          </div>
          <div className="dir__rows">
            {row.marks.map((mark) => (
              <div key={mark.date} className="dir__row">
                <span className="dir__what">
                  <b>
                    {t('{day}, {date}', {
                      day: formatWeekday(mark.date, 'short'),
                      date: formatDateLong(mark.date),
                    })}
                  </b>
                </span>
                <Chip tone={mark.came ? 'good' : 'bad'} size="sm">
                  {mark.came ? (mark.method === 'manual' ? t('вручную') : t('был')) : t('не был')}
                </Chip>
                <span />
              </div>
            ))}
          </div>
        </div>
      ))}
    </DataCard>
  )
}
