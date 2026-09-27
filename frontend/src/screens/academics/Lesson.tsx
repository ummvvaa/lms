/**
 * Урок: состав с отметками и оценками, тема и домашнее задание, итог урока.
 *
 * Главный сценарий учителя на телефоне: отметить отсутствующих или «Все
 * присутствуют», сохранить — касаниями по 44, без горизонтальной прокрутки.
 * Кымбат, администратор и куратор видят тот же экран на чтение; куратор
 * может напомнить учителю, Кымбат и администратор — открыть правку.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAcadMeta, useLessonDetail, useLessonMeta, useRemindLesson, useSaveAttendance, useSetGrade, type RosterRow } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import Field from '../../components/Field'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { absentWords, dateWords, MarkChip } from './shared'
import { RequestDialog } from './TeacherSchedule'
import LessonDrawer from './LessonDrawer'

function RosterLine({
  row,
  lessonId,
  kind,
  max,
  mayMark,
  mayGrade,
  locked,
  stream,
}: {
  row: RosterRow
  lessonId: number
  kind: 'fo' | 'sor' | 'soch'
  max: number
  mayMark: boolean
  mayGrade: boolean
  locked: boolean
  stream: boolean
}) {
  const attendance = useSaveAttendance()
  const grade = useSetGrade()
  const fail = (e: Error) => toast.error(e.message)
  const disabled = locked || !mayMark
  const options = kind === 'fo' ? Array.from({ length: max }, (_, i) => i + 1) : Array.from({ length: max + 1 }, (_, i) => max - i)
  return (
    <div className="roster__row">
      <div className="roster__who">
        <div className="roster__name">{row.full_name}</div>
        <div className="roster__note">
          {stream ? `${row.group} · ` : ''}
          {t('пропусков')} {row.absences} · {t('ФО')} {row.fo_avg ?? t('нет')}
          {row.excused ? ` · ${t('справка от куратора')}` : ''}
          {row.comment ? ` · «${row.comment}»` : ''}
        </div>
      </div>
      <div className="roster__ctl">
        <Segmented
          value={row.mark ?? 'present'}
          onChange={(mark) => !disabled && attendance.mutate({ lesson: lessonId, rows: [{ student: row.id, mark }] }, { onError: fail })}
          label={t('Отметка')}
          items={[
            { value: 'present', label: t('был') },
            { value: 'absent', label: t('н') },
            { value: 'late', label: t('оп') },
            ...(row.mark === 'excused' ? [{ value: 'excused', label: t('у') }] : []),
          ]}
        />
        {mayGrade ? (
          <div className="roster__grade">
            <Field
              kind="select"
              name={`grade-${row.id}`}
              label={kind === 'fo' ? t('Оценка') : t('Баллы')}
              value={row.grade === null ? '' : String(row.grade)}
              onChange={(next) => grade.mutate({ lesson: lessonId, student: row.id, value: next === '' ? null : Number(next) }, { onError: fail })}
              options={[{ value: '', title: kind === 'fo' ? t('балл') : `${t('из')} ${max}` }, ...options.map((n) => ({ value: String(n), title: String(n) }))]}
              disabled={locked}
            />
          </div>
        ) : (
          row.grade !== null && <Chip tone="neutral">{`${t('оценка')} ${row.grade}`}</Chip>
        )}
      </div>
    </div>
  )
}

export default function LessonScreen() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const lessonId = Number(id)
  const meta = useAcadMeta()
  const detail = useLessonDetail(Number.isFinite(lessonId) ? lessonId : null)
  const saveMeta = useLessonMeta()
  const attendance = useSaveAttendance()
  const remind = useRemindLesson()
  const [topic, setTopic] = useState('')
  const [homework, setHomework] = useState('')
  const [asking, setAsking] = useState(false)
  const [editing, setEditing] = useState(false)
  useEffect(() => {
    if (detail.data) {
      setTopic(detail.data.lesson.topic)
      setHomework(detail.data.lesson.homework)
    }
  }, [detail.data])

  if (detail.isLoading) return <Loading kind="cards" />
  if (detail.error) return <ErrorNote error={detail.error} />
  if (!detail.data) return null
  const data = detail.data
  const lesson = data.lesson
  const words = meta.data?.mark_words ?? {}
  const roster = data.roster ?? []
  const future = lesson.state === 'future'
  const locked = Boolean(data.locked) || future || !lesson.is_live
  const mayMark = Boolean(data.may_mark) && !locked
  const mayGrade = Boolean(data.may_grade) && !locked
  const max = lesson.kind === 'fo' ? (data.scale?.fo_max ?? 10) : (lesson.max_score ?? 10)
  const graded = roster.filter((row) => row.grade !== null)
  const fail = (e: Error) => toast.error(e.message)
  const statusChip = !lesson.is_live ? (
    <Chip tone="warn">{lesson.status_title}</Chip>
  ) : lesson.state === 'now' ? (
    <Chip tone="accent">{t('идёт сейчас')}</Chip>
  ) : future ? (
    <Chip>{t('впереди')}</Chip>
  ) : lesson.marked ? (
    <Chip tone="good">{t('отмечен')}</Chip>
  ) : (
    <Chip tone="warn">{t('не отмечен')}</Chip>
  )
  const back = me?.role === 'teacher' ? (data.course ? { label: t('Журнал'), to: `/journals/${data.course.id}` } : { label: t('Сегодня'), to: '/dashboard' }) : { label: t('Расписание'), to: '/schedule' }
  const saveTopic = () =>
    saveMeta.mutate({ lesson: lesson.id, topic, homework }, { onSuccess: () => toast.success(t('Тема и задание сохранены')), onError: fail })

  if (me?.role === 'student')
    return (
      <div>
        <ScreenHead title={lesson.subject.title} crumb={{ label: t('Расписание'), to: '/schedule' }} subtitle={`${lesson.weekday}, ${dateWords(lesson.date)} · ${lesson.slot} ${t('урок')}, ${lesson.bell} · ${lesson.room}`} />
        <DataCard title={t('Урок')}>
          <Rows>
            <Row title={t('Учитель')} value={lesson.actual_teacher?.full_name ?? ''} none={t('нет')} />
            <Row title={t('Моя отметка')} right={data.mine?.mark ? <MarkChip mark={data.mine.mark} words={words} /> : <span className="t-note">{future ? t('урок впереди') : t('учитель ещё не отметил')}</span>} />
            <Row title={t('Оценка')} value={data.mine?.grade ?? null} none={t('нет')} note={data.mine?.comment || undefined} />
            <Row title={t('Домашнее задание')} value={data.mine?.homework || null} none={t('не задано')} />
          </Rows>
        </DataCard>
      </div>
    )

  return (
    <div>
      <ScreenHead
        title={lesson.subject.title}
        crumb={back}
        pills={[{ label: lesson.cohort.name, on: true }, ...(lesson.kind !== 'fo' ? [{ label: `${lesson.kind_label} · ${t('из')} ${max}` }] : [])]}
        subtitle={`${lesson.weekday}, ${dateWords(lesson.date)} · ${lesson.slot} ${t('урок')}, ${lesson.bell} · ${lesson.room} · ${counted(roster.length, ['ученик', 'ученика', 'учеников'])}${
          lesson.substitute && lesson.teacher ? ` · ${t('замена за')} ${lesson.teacher.short}` : ''
        }`}
        actions={
          <>
            {mayMark && (
              <Button variant="outline" size="sm" onClick={() => attendance.mutate({ lesson: lesson.id, all_present: true }, { onSuccess: () => toast.success(t('Урок отмечен: все были')), onError: fail })}>
                {t('Все присутствуют')}
              </Button>
            )}
            {data.may_request && (
              <Button variant="outline" size="sm" onClick={() => setAsking(true)}>
                {t('Попросить перенос')}
              </Button>
            )}
            {data.may_remind && (
              <Button variant="outline" size="sm" onClick={() => remind.mutate(lesson.id, { onSuccess: (r) => toast.success(`${t('Напоминание ушло:')} ${r.reminded}`), onError: fail })}>
                {t('Напомнить учителю')}
              </Button>
            )}
            {data.may_edit && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                {t('Изменить урок')}
              </Button>
            )}
            {mayMark && (
              <Button size="sm" onClick={() => attendance.mutate({ lesson: lesson.id, rows: [] }, { onSuccess: () => { toast.success(lesson.marked ? t('Готово') : t('Урок отмечен')); navigate(back.to) }, onError: fail })}>
                {lesson.marked ? t('Готово') : t('Сохранить отметки')}
              </Button>
            )}
          </>
        }
      />
      <StatRow>
        <Kpi label={t('Состояние')} value={statusChip} />
        <Kpi label={t('Были')} value={lesson.marked ? `${roster.length - (data.absent?.length ?? 0)} ${t('из')} ${roster.length}` : null} none={future ? t('урок впереди') : t('не отмечен')} note={data.absent?.length ? absentWords(data.absent) : lesson.marked ? t('все на месте') : t('отметьте тех, кого нет')} tone={data.absent?.length ? 'bad' : lesson.marked ? 'good' : undefined} />
        <Kpi label={t('Опоздали')} value={data.late?.length || null} none={t('нет')} note={data.late?.join(', ') ?? ''} tone={data.late?.length ? 'warn' : undefined} />
        <Kpi label={t('Оценок')} value={graded.length || null} none={lesson.kind === 'fo' ? t('ФО ставится не всем') : t('нет')} note={graded.length ? `${t('средняя')} ${(graded.reduce((s, r) => s + (r.grade ?? 0), 0) / graded.length).toFixed(1)}` : ''} />
      </StatRow>
      {!lesson.is_live && (
        <Chip tone="warn">
          {`${lesson.status_title}${lesson.reason ? `: ${lesson.reason}` : ''}`}
        </Chip>
      )}
      <div className="acad__cols">
        <DataCard title={t('Состав')} count={roster.length} empty={roster.length === 0 && t('в составе нет учеников')} note={future ? t('Урок ещё впереди: отметить можно со звонка. Тему и домашнее задание можно записать заранее.') : data.locked ? `${t('Урок старше')} ${data.scale?.edit_days ?? 7} ${t('дней: отметки и оценки только для чтения. Исправление — через Кымбат.')}` : undefined}>
          <div className="roster">
            {roster.map((row) => (
              <RosterLine key={row.id} row={row} lessonId={lesson.id} kind={lesson.kind} max={max} mayMark={mayMark} mayGrade={mayGrade} locked={locked} stream={lesson.cohort.kind === 'stream'} />
            ))}
          </div>
        </DataCard>
        <div className="acad__stack">
          <DataCard title={t('Тема и домашнее задание')}>
            <Field kind="text" name="topic" label={t('Тема')} value={topic} onChange={setTopic} placeholder={t('О чём урок')} disabled={!data.may_grade && !data.may_edit} />
            <Field kind="textarea" name="homework" label={t('Домашнее задание')} value={homework} onChange={setHomework} rows={3} placeholder={t('Ученики увидят в расписании')} disabled={!data.may_grade && !data.may_edit} />
            {(data.may_grade || data.may_edit) && (
              <div className="acad__actions">
                <Button variant="secondary" size="sm" onClick={saveTopic} disabled={saveMeta.isPending}>
                  {t('Сохранить')}
                </Button>
              </div>
            )}
          </DataCard>
          <DataCard title={t('Урок')}>
            <Rows>
              <Row title={t('Учитель')} value={lesson.actual_teacher?.full_name ?? ''} none={t('нет')} note={lesson.substitute ? `${t('замена, основной')} ${lesson.teacher?.short ?? ''}` : undefined} />
              <Row title={t('Повтор')} value={data.repeat} />
              <Row
                title={t('Отметки')}
                value={lesson.marked && lesson.marked_by ? `${lesson.marked_by.short}` : null}
                none={future ? t('урок впереди') : t('учитель не отметил')}
                note={lesson.marked_at ? new Date(lesson.marked_at).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' }) : undefined}
              />
              {lesson.reason && <Row title={t('Причина')} value={lesson.reason} />}
            </Rows>
          </DataCard>
          {data.course && me?.role === 'teacher' && (
            <DataCard title={t('Журнал')}>
              <Rows>
                <Row icon="book" tone="accent" title={data.course.title} to={`/journals/${data.course.id}`} />
              </Rows>
            </DataCard>
          )}
        </div>
      </div>
      {asking && <RequestDialog lessons={[lesson]} initial={lesson.id} onClose={() => setAsking(false)} />}
      {editing && <LessonDrawer lesson={lesson} conflicts={data.conflicts ?? []} onClose={() => setEditing(false)} />}
    </div>
  )
}
