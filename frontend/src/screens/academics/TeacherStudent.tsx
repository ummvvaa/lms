/**
 * Ученик глазами учителя: имя, группа, куратор, оценки и пропуски по своим
 * предметам, последние уроки, уважительные причины. Больше ничего —
 * заметки кураторов, документы и поступление учителю не видны.
 */
import { useParams } from 'react-router'
import { useAcadMeta, useTeacherStudent } from '../../api/academics'
import EnglishLevel from './EnglishLevel'
import { Row, Rows, StatRow } from '../../components/patterns'
import { DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateShort, dateWords, MarkChip } from './shared'

export default function TeacherStudent() {
  const { id } = useParams()
  const studentId = Number(id)
  const meta = useAcadMeta()
  const { data, isLoading, error } = useTeacherStudent(Number.isFinite(studentId) ? studentId : null)
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const words = meta.data?.mark_words ?? {}
  return (
    <div>
      <ScreenHead
        title={data.student.full_name}
        crumb={{ label: t('Журналы'), to: '/journals' }}
        pills={[{ label: data.student.group, on: true }, ...[...new Set(data.courses.map((block) => block.course.cohort.short_name))].filter((name) => name !== data.student.group).map((label) => ({ label }))]}
      />
      <div className="acad__cols">
        <div className="acad__stack">
          {data.courses.map((block) => (
            <DataCard key={block.course.id} title={block.course.title}>
              <StatRow>
                <Kpi label={t('ФО')} value={block.stats.fo_avg} none={t('нет')} />
                <Kpi label={t('Пропуски')} value={block.stats.absent + block.stats.excused || null} none={t('нет')} />
                <Kpi label={t('СОР')} value={block.stats.sor_max ? `${block.stats.sor_got}/${block.stats.sor_max}` : null} none={t('не было')} />
                <Kpi label={t('Сейчас')} value={block.stats.final ?? block.stats.quarter_grade} none={t('мало оценок')} />
              </StatRow>
              <Rows>
                {block.recent.map((item) => (
                  <Row
                    key={item.lesson.id}
                    lead={<b className="num">{Number(item.lesson.date.slice(8))}</b>}
                    title={item.lesson.topic || t('Урок')}
                    note={`${item.lesson.weekday}, ${dateWords(item.lesson.date)}`}
                    right={<MarkChip mark={item.mark} words={words} size="sm" lateBy={item.late_by} lateAsAbsent={item.late_as_absent} />}
                    value={item.grade}
                    none={t('нет')}
                    to={`/lessons/${item.lesson.id}`}
                  />
                ))}
              </Rows>
            </DataCard>
          ))}
        </div>
        <div className="acad__stack">
          {data.english && <EnglishLevel student={data.student.id} info={data.english} />}
          <DataCard title={t('Куратор группы')}>
            <Rows>
              <Row
                avatar={data.curator?.full_name ?? '?'}
                title={data.curator?.full_name ?? t('не назначен')}
                note={t('куратор {group}', { group: data.student.group })}
                acts={
                  data.curator_email ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => window.open(`mailto:${data.curator_email}?subject=${encodeURIComponent(data.student.full_name)}`, '_self')}
                    >
                      {t('Написать')}
                    </Button>
                  ) : undefined
                }
              />
            </Rows>
          </DataCard>
          <DataCard title={t('Уважительные причины')} count={data.excuses.length || undefined} empty={data.excuses.length === 0 && t('не оформлялись')}>
            <Rows>
              {data.excuses.map((row) => (
                <Row key={row.id} icon="doc" tone="info" title={`${row.reason} · ${dateShort(row.starts)}–${dateShort(row.ends)}`} note={`${row.document_title} · ${t('оформил {name}', { name: row.created_by })}`} />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
