/**
 * Блок «Секция» в карточке ученика у куратора (макет CStudents, 27.10.2026):
 * где и когда занимается, посещение за месяц, последние отметки. Только
 * чтение — записывает и переводит директор спорта.
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
        title={t('Секция')}
        empty={t('не записан ни в одну секцию · записать может директор спорта')}
      />
    )
  return (
    <DataCard title={t('Секция')} note={t('Только просмотр · записывает и переводит директор спорта')}>
      <div className="dir__lines">
        <div className="dir__line">
          <span>{data.section}</span>
          <b>{data.slot || t('час не выбран')}</b>
        </div>
        <div className="dir__line">
          <span>{t('Адрес')}</span>
          <b>{data.address}</b>
        </div>
        <div className="dir__line">
          <span>{t('Посещение за месяц')}</span>
          {data.percent === null || data.percent === undefined ? (
            <b>{t('занятий не было')}</b>
          ) : data.below ? (
            <Chip tone="warn" size="sm" className="num">{`${data.percent}%`}</Chip>
          ) : (
            <b className="num">{data.percent}%</b>
          )}
        </div>
      </div>
      <div className="dir__rows">
        {(data.marks ?? []).map((mark) => (
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
    </DataCard>
  )
}
