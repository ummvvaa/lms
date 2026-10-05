/**
 * Урок: состав с отметками и оценками, тема и домашнее задание, итог урока.
 *
 * Главный сценарий учителя на телефоне: отметить отсутствующих или «Все
 * присутствуют», сохранить — касаниями по 44, без горизонтальной прокрутки.
 * Кымбат, администратор и куратор видят тот же экран на чтение; куратор
 * может напомнить учителю, Кымбат и администратор — открыть правку.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useAcadMeta, useLessonDetail, useRemindLesson, useSaveAttendance, type RosterRow } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'
import { SelectField } from '../../components/SelectField'
import { t, tn } from '../../i18n'
import { absentWords, ArrivalForm, dateWords, GRADE_COMMENT_HINT, GRADE_COMMENT_MAX, lateWords, MarkChip, useGradeComment } from './shared'
import { RequestDialog } from './TeacherSchedule'
import LessonDrawer from './LessonDrawer'
import LessonHomeworkCards from './LessonHomework'
import { homeworkReviewOpen } from '../../layout/nav'
import { LessonHomeworkRow } from '../homework/LessonHomeworkRow'
import { formatDateTime } from '../../lib/format'

/** Отметка на чтение: слово отметки, у неотмеченного урока — «не отмечен». */
function MarkCell({ row, words }: { row: RosterRow; words: Record<string, string> }) {
  if (row.mark === null) return <span className="roster__none">{t('не отмечен')}</span>
  return <MarkChip mark={row.mark} words={words} lateBy={row.late_by} lateAsAbsent={row.late_as_absent} size="sm" />
}

/**
 * Строка состава — постоянные колонки: ученик | посещаемость | оценка |
 * комментарий. Нет оценки или комментария — серое «нет» на своём месте,
 * соседние колонки не сдвигаются (30.09.2026).
 */
function RosterLine({
  row,
  lessonId,
  kind,
  max,
  mayMark,
  mayGrade,
  locked,
  stream,
  state,
  words,
}: {
  row: RosterRow
  lessonId: number
  state: 'past' | 'now' | 'future'
  kind: 'fo' | 'sor' | 'soch'
  max: number
  mayMark: boolean
  mayGrade: boolean
  locked: boolean
  stream: boolean
  words: Record<string, string>
}) {
  const attendance = useSaveAttendance()
  // «опоздал» ставится со временем прихода: сначала поле «Пришёл в», потом запрос
  const [askLate, setAskLate] = useState(false)
  const grade = useGradeComment({ lesson: lessonId, student: row.id, value: row.grade, comment: row.comment })
  const fail = (e: Error) => toast.error(e.message)
  const disabled = locked || !mayMark
  const options = kind === 'fo' ? Array.from({ length: max }, (_, i) => i + 1) : Array.from({ length: max + 1 }, (_, i) => max - i)
  const gradeLabel = kind === 'fo' ? t('Оценка') : t('Баллы из {max}', { max })
  return (
    <div className="roster__row">
      <div className="roster__who">
        <div className="roster__name">{row.full_name}</div>
        <div className="roster__note">
          {[
            stream ? row.group : '',
            t('пропусков: {n}', { n: row.absences }),
            t('ФО {value}', { value: row.fo_avg ?? t('нет') }),
            row.excused ? t('справка от куратора') : '',
            row.mark === 'late' ? (row.arrived ? `${lateWords(row.late_by)}, ${t('пришёл в {time}', { time: row.arrived })}` : lateWords(row.late_by)) : '',
          ]
            .filter(Boolean)
            .join(' · ')}
        </div>
        {row.mark === 'late' && !disabled && !askLate && (
          <Button variant="link" size="sm" onClick={() => setAskLate(true)}>
            {t('Изменить время прихода')}
          </Button>
        )}
        {askLate && !disabled && (
          <ArrivalForm
            state={state}
            arrived={row.arrived}
            busy={attendance.isPending}
            onCancel={() => setAskLate(false)}
            onSubmit={(arrived) =>
              attendance.mutate({ lesson: lessonId, rows: [{ student: row.id, mark: 'late', arrived }] }, { onSuccess: () => setAskLate(false), onError: fail })
            }
          />
        )}
      </div>
      <div className="roster__att">
        {mayMark ? (
          <Segmented
            value={row.mark ?? 'present'}
            onChange={(mark) => {
              if (disabled) return
              if (mark === 'late') setAskLate(true)
              else {
                setAskLate(false)
                attendance.mutate({ lesson: lessonId, rows: [{ student: row.id, mark }] }, { onError: fail })
              }
            }}
            label={t('Отметка')}
            items={[
              { value: 'present', label: t('был') },
              { value: 'absent', label: t('н') },
              { value: 'late', label: t('оп') },
              ...(row.mark === 'excused' ? [{ value: 'excused', label: t('у') }] : []),
            ]}
          />
        ) : (
          <MarkCell row={row} words={words} />
        )}
      </div>
      <div className="roster__grade">
        {mayGrade ? (
          <SelectField
            size="sm"
            aria-label={`${gradeLabel}: ${row.full_name}`}
            value={row.grade === null ? '' : String(row.grade)}
            onChange={(event) => grade.putValue(event.target.value === '' ? null : Number(event.target.value))}
            disabled={locked || grade.busy}
          >
            <option value="">{kind === 'fo' ? t('нет') : t('из {max}', { max })}</option>
            {options.map((n) => (
              <option key={n} value={String(n)}>
                {n}
              </option>
            ))}
          </SelectField>
        ) : row.grade !== null ? (
          <b className="num">{row.grade}</b>
        ) : (
          <span className="roster__none">{t('нет')}</span>
        )}
      </div>
      <div className="roster__comment">
        {mayGrade ? (
          <div className="roster__commentedit">
            <Textarea
              aria-label={`${t('Комментарий к оценке')}: ${row.full_name}`}
              rows={1}
              value={grade.draft}
              onChange={(event) => grade.setDraft(event.target.value)}
              onKeyDown={(event) => {
                // Enter сохраняет, Shift+Enter — новая строка
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  grade.saveComment()
                }
              }}
              placeholder={row.grade === null ? t('Сначала оценка, потом почему') : t('Почему такая оценка')}
              maxLength={GRADE_COMMENT_MAX}
              disabled={locked}
            />
            {grade.dirty && row.grade !== null && (
              <Button size="sm" variant="secondary" disabled={grade.busy} onClick={grade.saveComment}>
                {t('Сохранить')}
              </Button>
            )}
          </div>
        ) : row.comment ? (
          <span className="roster__text">{row.comment}</span>
        ) : (
          <span className="roster__none">{t('нет')}</span>
        )}
      </div>
    </div>
  )
}

/** Шапка состава: те же колонки, что у строк. */
function RosterHead({ kind, max, mayGrade }: { kind: 'fo' | 'sor' | 'soch'; max: number; mayGrade: boolean }) {
  return (
    <div className="roster__head" aria-hidden="true">
      <span className="t-caps">{t('Ученик')}</span>
      <span className="t-caps">{t('Посещаемость')}</span>
      <span className="t-caps">{kind === 'fo' ? t('Оценка') : t('Баллы из {max}', { max })}</span>
      <span className="roster__headcomment">
        <span className="t-caps">{t('Комментарий к оценке')}</span>
        {mayGrade && <span className="t-note">{t(GRADE_COMMENT_HINT)}</span>}
      </span>
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
  const attendance = useSaveAttendance()
  const remind = useRemindLesson()
  const [asking, setAsking] = useState(false)
  const [editing, setEditing] = useState(false)

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

  if (me?.role === 'student')
    return (
      <div>
        <ScreenHead title={lesson.subject.title} crumb={{ label: t('Расписание'), to: '/schedule' }} subtitle={`${lesson.weekday}, ${dateWords(lesson.date)} · ${t('{slot} урок', { slot: lesson.slot })}, ${lesson.bell} · ${lesson.room}`} />
        <DataCard title={t('Урок')}>
          <Rows>
            <Row title={t('Учитель')} value={lesson.actual_teacher?.full_name ?? ''} none={t('не назначен')} />
            <Row title={t('Моя отметка')} right={data.mine?.mark ? <MarkChip mark={data.mine.mark} words={words} lateBy={data.mine.late_by} lateAsAbsent={data.mine.late_as_absent} /> : <span className="t-note">{future ? t('урок впереди') : t('учитель ещё не отметил')}</span>} />
            <Row title={t('Оценка')} value={data.mine?.grade ?? null} none={t('нет')} note={data.mine?.comment || undefined} />
            <LessonHomeworkRow lesson={lesson.id} text={data.mine?.homework ?? ''} />
          </Rows>
        </DataCard>
      </div>
    )

  return (
    <div>
      <ScreenHead
        title={lesson.subject.title}
        crumb={back}
        pills={[{ label: lesson.cohort.name, on: true }, ...(lesson.kind !== 'fo' ? [{ label: `${lesson.kind_label} · ${t('из {max}', { max })}` }] : [])]}
        subtitle={[
          `${lesson.weekday}, ${dateWords(lesson.date)}`,
          `${t('{slot} урок', { slot: lesson.slot })}, ${lesson.bell}`,
          lesson.room,
          counted(roster.length, 'ученик|ученика|учеников'),
          lesson.substitute && lesson.teacher ? t('замена за {teacher}', { teacher: lesson.teacher.short }) : '',
        ]
          .filter(Boolean)
          .join(' · ')}
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
        <Kpi label={t('Были')} value={lesson.marked ? t('{done} из {total}', { done: roster.length - (data.absent?.length ?? 0), total: roster.length }) : null} none={future ? t('урок впереди') : t('не отмечен')} note={data.absent?.length ? absentWords(data.absent) : lesson.marked ? t('все на месте') : t('отметьте тех, кого нет')} tone={data.absent?.length ? 'bad' : lesson.marked ? 'good' : undefined} />
        <Kpi label={t('Опоздали')} value={data.late?.length || null} none={t('нет')} note={data.late?.join(', ') ?? ''} tone={data.late?.length ? 'warn' : undefined} />
        <Kpi label={t('Оценок')} value={graded.length || null} none={lesson.kind === 'fo' ? t('ФО ставится не всем') : t('нет')} note={graded.length ? t('средняя {value}', { value: (graded.reduce((s, r) => s + (r.grade ?? 0), 0) / graded.length).toFixed(1) }) : ''} />
      </StatRow>
      {!lesson.is_live && (
        <Chip tone="warn">
          {`${lesson.status_title}${lesson.reason ? `: ${lesson.reason}` : ''}`}
        </Chip>
      )}
      {/* Состав на всю ширину, под ним тема и ДЗ | «Кто получит», «Урок»,
          «Журнал». На телефоне: состав → тема и ДЗ → остальное (30.09.2026) */}
      <LessonHomeworkCards lesson={lesson} mayWrite={Boolean(data.may_grade || data.may_edit)} lms={Boolean(me && homeworkReviewOpen(me.role, me.teaches))}>
        {(topic, recipients) => (
          <div className="lesson__grid">
            <div className="lesson__roster">
              <DataCard title={t('Состав')} count={roster.length} empty={roster.length === 0 && t('в составе нет учеников')} note={future ? t('Урок ещё впереди: отметить можно со звонка. Тему и домашнее задание можно записать заранее.') : data.locked ? tn(data.scale?.edit_days ?? 7, 'Урок старше {n} дня: отметки и оценки только для чтения. Исправление — через Кымбат.|Урок старше {n} дней: отметки и оценки только для чтения. Исправление — через Кымбат.|Урок старше {n} дней: отметки и оценки только для чтения. Исправление — через Кымбат.') : undefined}>
                {roster.length > 0 && (
                  <div className="roster">
                    <RosterHead kind={lesson.kind} max={max} mayGrade={mayGrade} />
                    {roster.map((row) => (
                      <RosterLine key={row.id} row={row} lessonId={lesson.id} kind={lesson.kind} max={max} mayMark={mayMark} mayGrade={mayGrade} locked={locked} stream={lesson.cohort.kind === 'stream'} state={lesson.state} words={words} />
                    ))}
                  </div>
                )}
              </DataCard>
            </div>
            <div className="lesson__topic">{topic}</div>
            <div className="lesson__rest acad__stack">
              {recipients}
              <DataCard title={t('Урок')}>
                <Rows>
                  <Row title={t('Учитель')} value={lesson.actual_teacher?.full_name ?? ''} none={t('не назначен')} note={lesson.substitute ? t('замена, основной {teacher}', { teacher: lesson.teacher?.short ?? '' }) : undefined} />
                  <Row title={t('Повтор')} value={data.repeat} />
                  <Row
                    title={t('Отметки')}
                    value={lesson.marked && lesson.marked_by ? `${lesson.marked_by.short}` : null}
                    none={future ? t('урок впереди') : t('учитель не отметил')}
                    note={lesson.marked_at ? formatDateTime(lesson.marked_at) : undefined}
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
        )}
      </LessonHomeworkCards>
      {asking && <RequestDialog lessons={[lesson]} initial={lesson.id} onClose={() => setAsking(false)} />}
      {editing && <LessonDrawer lesson={lesson} conflicts={data.conflicts ?? []} onClose={() => setEditing(false)} />}
    </div>
  )
}
