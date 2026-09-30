/**
 * Вкладка «Успеваемость» в карточке ученика: по предметам, посещаемость
 * по дням, уважительные причины. У куратора и администратора — кнопка
 * «Оформить причину» (сервер говорит `may_excuse`).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { gradeTone, useAddExcuse, useDropExcuse, useStudentGrades } from '../../api/academics'
import EnglishLevel from './EnglishLevel'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateShort, dateWords, lateTotal, PeriodSwitch } from './shared'
import { HomeworkKpi } from '../homework/myWork'

export function ExcuseDialog({ student, from, to, onClose }: { student: number; from?: string; to?: string; onClose: () => void }) {
  const add = useAddExcuse()
  const [starts, setStarts] = useState(from ?? '')
  const [ends, setEnds] = useState(to ?? from ?? '')
  const [reason, setReason] = useState(t('Болезнь'))
  const [document, setDocument] = useState('certificate')
  const [error, setError] = useState('')
  return (
    <Modal title={t('Уважительная причина')} note={t('Пропуски «н» в эти дни станут «у» во всех журналах')} onClose={onClose}>
      <Field.Row>
        <Field kind="date" name="starts" label={t('С')} value={starts} onChange={setStarts} />
        <Field kind="date" name="ends" label={t('По')} value={ends} onChange={setEnds} />
      </Field.Row>
      <Field kind="text" name="reason" label={t('Причина')} value={reason} onChange={setReason} error={error || undefined} />
      <Field
        kind="select"
        name="document"
        label={t('Документ')}
        value={document}
        onChange={setDocument}
        options={[
          { value: 'certificate', title: t('Справка') },
          { value: 'parents', title: t('Заявление родителей') },
          { value: 'order', title: t('Приказ школы') },
          { value: 'other', title: t('Другое') },
        ]}
      />
      <div className="acad__actions">
        <Button
          onClick={() =>
            add.mutate(
              { student, starts, ends: ends || starts, reason, document },
              {
                onSuccess: () => {
                  toast.success(t('Причина оформлена: пропуски стали «у»'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={!starts || add.isPending}
        >
          {t('Оформить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

export default function GradesTab({ studentId }: { studentId: number }) {
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useStudentGrades(studentId, period)
  const drop = useDropExcuse()
  const [excusing, setExcusing] = useState<{ from?: string; to?: string } | null>(null)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const unexcused = data.unexcused_days ?? []
  return (
    <div>
      <div className="acad__toolbar">
        <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
        {data.may_excuse && (
          <Button size="sm" onClick={() => setExcusing({ from: unexcused[0], to: unexcused[unexcused.length - 1] })}>
            {t('Уважительная причина')}
          </Button>
        )}
      </div>
      <StatRow>
        <Kpi label={t('Посещаемость')} value={data.attendance.pct !== null ? `${data.attendance.pct} %` : null} none={t('уроков с отметкой не было')} note={`${t('уроков')} ${data.attendance.total}`} />
        <Kpi label={t('Без причины')} value={data.attendance.absent || null} none={t('нет')} tone={data.attendance.absent ? 'bad' : undefined} action={data.may_excuse && unexcused.length ? { label: t('Оформить'), onClick: () => setExcusing({ from: unexcused[0], to: unexcused[unexcused.length - 1] }) } : undefined} />
        <Kpi label={t('По уважительной')} value={data.attendance.excused || null} none={t('нет')} />
        <Kpi label={t('Опоздания')} value={data.attendance.late || null} none={t('нет')} note={lateTotal(data.attendance)} />
        <HomeworkKpi homework={data.homework} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('По предметам')} count={data.subjects.length || undefined} empty={data.subjects.length === 0 && t('журналов с этим учеником пока нет')}>
            <Rows>
              {data.subjects.map((item) => {
                const s = item.stats
                const grade = s.final ?? s.quarter_grade
                return (
                  <Row
                    key={item.course.id}
                    icon="book"
                    tone="neutral"
                    title={item.course.subject.title}
                    note={[s.fo_avg !== null ? `${t('ФО')} ${s.fo_avg}` : '', s.sor_max ? `${t('СОР')} ${s.sor_got}/${s.sor_max}` : '', s.soch_max ? `${t('СОЧ')} ${s.soch_got}/${s.soch_max}` : '', `${t('пропусков')} ${s.absent + s.excused}`].filter(Boolean).join(' · ')}
                    right={
                      item.course.subject.scheme === 'kz' ? (
                        grade !== null ? (
                          <Chip tone={gradeTone(grade) as Tone}>{s.final !== null ? `${t('итог')} ${grade}` : `${t('выходит')} ${grade}`}</Chip>
                        ) : (
                          <Chip tone="neutral">{t('мало оценок')}</Chip>
                        )
                      ) : undefined
                    }
                  />
                )
              })}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          {data.english && <EnglishLevel student={studentId} info={data.english} />}
          <DataCard title={t('Дни с пропусками')} count={data.days.length || undefined} empty={data.days.length === 0 && t('пропусков нет')}>
            <Rows>
              {data.days.map((day) => (
                <Row
                  key={day.date}
                  lead={<b className="num">{Number(day.date.slice(8))}</b>}
                  tone={day.has_absent ? 'bad' : 'info'}
                  title={`${day.weekday}, ${dateWords(day.date)}`}
                  note={day.marks.map((m) => `${m.subject} ${m.mark === 'absent' ? 'н' : m.mark === 'excused' ? 'у' : 'оп'}`).join(', ')}
                  acts={data.may_excuse && day.has_absent ? <Button variant="secondary" size="sm" onClick={() => setExcusing({ from: day.date, to: day.date })}>{t('Оформить')}</Button> : undefined}
                />
              ))}
            </Rows>
          </DataCard>
          {data.excuses && (
            <DataCard title={t('Уважительные причины')} count={data.excuses.length || undefined} empty={data.excuses.length === 0 && t('не оформлялись')}>
              <Rows>
                {data.excuses.map((row) => (
                  <Row
                    key={row.id}
                    icon="doc"
                    tone="info"
                    title={`${row.reason} · ${dateShort(row.starts)}${row.ends !== row.starts ? `–${dateShort(row.ends)}` : ''}`}
                    note={`${row.document_title} · ${t('оформил')} ${row.created_by}`}
                    acts={data.may_excuse ? <Button variant="outline" size="sm" onClick={() => drop.mutate(row.id, { onSuccess: () => toast.success(t('Причина снята')), onError: (e) => toast.error(e.message) })}>{t('Снять')}</Button> : undefined}
                  />
                ))}
              </Rows>
            </DataCard>
          )}
        </div>
      </div>
      {excusing && <ExcuseDialog student={studentId} from={excusing.from} to={excusing.to} onClose={() => setExcusing(null)} />}
    </div>
  )
}
