/**
 * Журнал: слева ученики, по верху уроки, в клетке отметка и оценка рядом;
 * справа пропуски, средний ФО, СОР, СОЧ и «сейчас выходит».
 *
 * Матрица — общий `Matrix` с клавиатурой: цифра — оценка (0 — десять),
 * «н» и «о» — отметка, Backspace — снять, стрелки — соседняя клетка.
 * Выделенная клетка правится и в карточке под журналом: отметка, оценка,
 * комментарий. На телефоне матрицы нет — уроки списком, каждый открывает
 * экран урока. Учитель — свой журнал, Кымбат, администратор и куратор —
 * на чтение (сервер говорит `may_edit`).
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  foTone,
  gradeTone,
  useAcadMeta,
  useJournal,
  useJournalFinal,
  useLessonMeta,
  useSaveAttendance,
  useSetGrade,
  type AcadMark,
  type Journal as JournalData,
  type JournalCell,
  type JournalColumn,
  type JournalHomeworkCell,
} from '../../api/academics'
import Field from '../../components/Field'
import Matrix, { type MatrixCell, type MatrixColumn, type MatrixRow, type MatrixTone } from '../../components/Matrix'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { ExportPreview } from '../../components/ExportPreview'
import Icon from '../../layout/icons'
import { homeworkReviewOpen } from '../../layout/nav'
import { useAuth } from '../../auth/AuthContext'
import { t, tk, tn } from '../../i18n'
import { usePhone } from '../../phone'
import { ArrivalForm, dateShort, dateWords, GRADE_COMMENT_HINT, GRADE_COMMENT_MAX, lateWords, MarkChip, PeriodSwitch, useGradeComment } from './shared'
import './homework-review.css'

type Mode = 'both' | 'a' | 'g'

const MARK_SHORT: Record<string, string> = { absent: tk('н'), excused: tk('у'), late: tk('оп') }

function cellNode(cell: JournalCell, column: JournalColumn, mode: Mode) {
  if (column.future) return <span className="jcell" />
  const mark = cell.mark
  const showMark = mode !== 'g'
  const showGrade = mode !== 'a'
  // подсказка клетки: «опоздал на 12 мин» и комментарий к оценке
  const hint = [mark === 'late' ? lateWords(cell.late_by) : '', cell.comment].filter(Boolean).join(' · ')
  return (
    <span className="jcell" title={hint || undefined}>
      {showMark &&
        (mark === null ? (
          <i className="jcell__a" />
        ) : mark === 'present' ? (
          <i className="jcell__a jcell__dot">·</i>
        ) : (
          <i className={`jcell__a jcell__a--${mark}`}>{MARK_SHORT[mark] ? t(MARK_SHORT[mark]) : ''}</i>
        ))}
      {showGrade && cell.grade !== null && (
        <b className="jcell__g num">
          {cell.grade}
          {column.kind !== 'fo' && column.max_score ? <span className="jcell__max">/{column.max_score}</span> : ''}
          {cell.comment ? <span className="jcell__max">*</span> : ''}
        </b>
      )}
    </span>
  )
}

/**
 * Клетка «ДЗ» — только чтение: оценка, «✓» без оценки, «сдано» (ждёт проверки,
 * у опоздавшей работы — «опозд.»), «—» не сдано после срока, пусто — срок идёт.
 * Сданная работа открывается кликом в «Проверке ДЗ».
 */
function homeworkNode(cell: JournalHomeworkCell | undefined, to: string | null) {
  if (!cell || cell.state === 'pending') return <span className="jhw" />
  if (cell.state === 'missed')
    return (
      <span className="jhw jhw__miss" title={t('ДЗ не сдано')}>
        —
      </span>
    )
  const inner =
    cell.state === 'checked' ? (
      cell.grade !== null ? (
        <b className="num">{cell.grade}</b>
      ) : (
        <span className="jhw__chk">✓</span>
      )
    ) : (
      <Chip tone={cell.late ? 'warn' : 'accent'} size="sm">
        {cell.late ? t('опозд.') : t('сдано')}
      </Chip>
    )
  const hint = cell.late ? t('сдано с опозданием') : undefined
  // куратор журнал читает, а «Проверки ДЗ» у него нет — клетка без перехода
  if (to === null)
    return (
      <span className="jhw" title={hint}>
        {inner}
      </span>
    )
  return (
    <Link className="jhw" to={to} title={hint}>
      {inner}
    </Link>
  )
}

/** Колонка матрицы: урок, «ДЗ» урока или сводка справа. */
type Slot = { kind: 'lesson'; index: number } | { kind: 'hw'; index: number; lesson: number } | { kind: 'sum'; key: string }

function cellTone(cell: { mark: AcadMark; grade: number | null }, column: JournalColumn, foMax: number): MatrixTone | undefined {
  if (column.future) return undefined
  if (cell.grade !== null) {
    const tone = column.kind === 'fo' ? foTone(cell.grade, foMax) : foTone(cell.grade, column.max_score ?? foMax)
    return tone === 'neutral' ? undefined : tone
  }
  if (cell.mark === 'absent') return 'bad'
  if (cell.mark === 'excused') return 'info'
  if (cell.mark === 'late') return 'warn'
  return undefined
}

/**
 * Правка выделенной клетки: отметка, оценка, комментарий.
 *
 * Оценка ставится сразу по нажатию — вместе с уже набранным комментарием;
 * комментарий к стоящей оценке — одной кнопкой «Сохранить». Кнопки живы
 * только там, где сервер примет запись (`may_grade`, `may_mark` колонки);
 * иначе рядом сказано, кто ставит оценку этого урока.
 */
function CellEditor({
  journal,
  cell,
  onClose,
  askLateFirst = false,
}: {
  journal: JournalData
  cell: MatrixCell
  onClose: () => void
  /** «оп» с клавиатуры на прошедшем уроке: сразу спросить время прихода */
  askLateFirst?: boolean
}) {
  const row = journal.rows[cell.row]
  const column = journal.columns[cell.col]
  const value = row?.cells[cell.col]
  const attendance = useSaveAttendance()
  const grade = useGradeComment({ lesson: column?.lesson ?? 0, student: row?.id ?? 0, value: value?.grade ?? null, comment: value?.comment ?? '' })
  const [askLate, setAskLate] = useState(askLateFirst)
  useEffect(() => setAskLate(askLateFirst), [askLateFirst, cell.row, cell.col])
  const [score, setScore] = useState(value?.grade === null || value?.grade === undefined ? '' : String(value.grade))
  useEffect(() => {
    setScore(value?.grade === null || value?.grade === undefined ? '' : String(value.grade))
  }, [value?.grade])
  if (!row || !column || !value) return null
  const locked = column.locked || column.future || !journal.may_edit
  const markLocked = locked || !column.may_mark
  const gradeLocked = locked || !column.may_grade
  const fail = (e: Error) => toast.error(e.message)
  const setMark = (mark: string) => attendance.mutate({ lesson: column.lesson, rows: [{ student: row.id, mark }] }, { onError: fail })
  const max = column.kind === 'fo' ? journal.scale.fo_max : (column.max_score ?? journal.scale.fo_max)
  const why = column.future
    ? t('урок впереди: оценки и отметки — со звонка')
    : column.locked
      ? tn(journal.scale.edit_days, 'старше {n} дня — правит Кымбат|старше {n} дней — правит Кымбат|старше {n} дней — правит Кымбат')
      : !column.may_grade && column.teacher
        ? t('оценку ставит тот, кто вёл урок: {teacher}', { teacher: column.teacher })
        : !column.may_grade
          ? t('у урока нет учителя — оценку ставит Кымбат или администратор')
          : ''
  return (
    <DataCard
      title={row.full_name}
      note={`${column.weekday}, ${dateWords(column.date)} · ${t('{slot} урок', { slot: column.slot })} · ${column.kind_label}${why ? ` · ${why}` : ''}`}
      right={
        <Button variant="outline" size="sm" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      }
    >
      <div className="jedit">
        <div>
          <span className="t-caps">{t('Посещаемость')}</span>
          <Segmented
            value={value.mark ?? 'present'}
            onChange={(next) => {
              if (markLocked) return
              if (next === 'late') setAskLate(true)
              else {
                setAskLate(false)
                setMark(next)
              }
            }}
            label={t('Отметка')}
            items={[
              { value: 'present', label: t('был') },
              { value: 'absent', label: t('н') },
              { value: 'late', label: t('оп') },
              ...(value.mark === 'excused' ? [{ value: 'excused', label: t('у') }] : []),
            ]}
          />
          {value.mark === 'late' && !askLate && (
            <span className="t-note">
              {lateWords(value.late_by)}
              {value.arrived ? `, ${t('пришёл в {time}', { time: value.arrived })}` : ''}
              {!markLocked && (
                <Button variant="link" size="sm" onClick={() => setAskLate(true)}>
                  {t('Изменить время прихода')}
                </Button>
              )}
            </span>
          )}
          {askLate && !markLocked && (
            <ArrivalForm
              key={`${cell.row}-${cell.col}`}
              state={column.state}
              arrived={value.arrived}
              busy={attendance.isPending}
              onCancel={() => setAskLate(false)}
              onSubmit={(arrived) =>
                attendance.mutate({ lesson: column.lesson, rows: [{ student: row.id, mark: 'late', arrived }] }, { onSuccess: () => setAskLate(false), onError: fail })
              }
            />
          )}
        </div>
        <div>
          <span className="t-caps">{column.kind === 'fo' ? t('Оценка ФО') : t('{kind}, баллы из {max}', { kind: column.kind_label, max })}</span>
          {column.kind === 'fo' ? (
            <div className="jedit__grades">
              {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
                <Button key={n} variant={value.grade === n ? 'default' : 'outline'} size="sm" disabled={gradeLocked || grade.busy} onClick={() => grade.putValue(n)}>
                  {n}
                </Button>
              ))}
            </div>
          ) : (
            <Field.Row>
              <Field kind="number" name="score" label={t('Баллы')} value={score} onChange={setScore} min={0} max={max} disabled={gradeLocked} />
              <Button size="sm" disabled={gradeLocked || score === '' || grade.busy} onClick={() => grade.putValue(Number(score))}>
                {t('Поставить')}
              </Button>
            </Field.Row>
          )}
        </div>
        <div>
          <Field
            kind="textarea"
            name="comment"
            label={t('Комментарий к оценке')}
            value={grade.draft}
            onChange={grade.setDraft}
            rows={3}
            placeholder={value.grade === null ? t('Выберите оценку — и напишите, почему такая') : t('Почему такая оценка')}
            hint={`${t(GRADE_COMMENT_HINT)} · ${grade.draft.length}/${GRADE_COMMENT_MAX}`}
            disabled={gradeLocked}
          />
          <div className="acad__actions">
            <Button size="sm" disabled={gradeLocked || value.grade === null || !grade.dirty || grade.busy} onClick={grade.saveComment}>
              {t('Сохранить')}
            </Button>
            <Button variant="link" size="sm" disabled={gradeLocked || value.grade === null || grade.busy} onClick={() => grade.putValue(null)}>
              {t('Снять оценку')}
            </Button>
          </div>
        </div>
      </div>
    </DataCard>
  )
}

/** Итог четверти: по ученику расчёт и выбор, отличие требует причины. */
function FinalDialog({ journal, onClose }: { journal: JournalData; onClose: () => void }) {
  const finals = useJournalFinal()
  const [picked, setPicked] = useState<Record<number, string>>(() =>
    Object.fromEntries(journal.rows.map((row) => [row.id, String(row.stats.final ?? row.stats.quarter_grade ?? '')])),
  )
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const quarter = journal.quarter
  if (!quarter) return null
  const submit = () => {
    finals.mutate(
      {
        course: journal.course.id,
        quarter: quarter.id,
        rows: journal.rows.map((row) => ({ student: row.id, final: picked[row.id] ? Number(picked[row.id]) : null, reason })),
      },
      {
        onSuccess: () => {
          toast.success(t('Итог выставлен. Попадёт в отчёт родителям за четверть'))
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  return (
    <Modal title={t('Итог за {quarter}', { quarter: quarter.title })} note={journal.course.title} onClose={onClose} wide>
      <p className="acad__note">
        {quarter.closed
          ? t('Приём итогов закрыт. Изменить итог может только Кымбат или администратор.')
          : t('Четверть идёт до {date}. Обычно итог выставляют в последнюю неделю. Можно поправить расчёт — тогда нужна причина.', {
              date: dateWords(quarter.ends),
            })}
      </p>
      <Rows>
        {journal.rows.map((row) => (
          <Row
            key={row.id}
            avatar={row.full_name}
            title={row.full_name}
            note={row.stats.quarter_pct !== null ? t('по расчёту {pct} % → {mark}', { pct: row.stats.quarter_pct, mark: row.stats.quarter_grade }) : t('оценок мало для расчёта')}
            right={
              <Field
                kind="select"
                name={`g${row.id}`}
                label={t('Итог')}
                value={picked[row.id] ?? ''}
                onChange={(next) => setPicked((old) => ({ ...old, [row.id]: next }))}
                options={[
                  { value: '', title: t('нет') },
                  ...[5, 4, 3, 2].map((n) => ({ value: String(n), title: String(n) })),
                ]}
                disabled={quarter.closed && !journal.may_edit}
              />
            }
          />
        ))}
      </Rows>
      <Field kind="text" name="reason" label={t('Причина, если меняли расчёт')} value={reason} onChange={setReason} error={error || undefined} />
      <div className="acad__actions">
        <Button onClick={submit} disabled={finals.isPending}>
          {t('Выставить итог')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Запланировать СОР или СОЧ на будущий урок. */
function AssessmentDialog({ journal, onClose }: { journal: JournalData; onClose: () => void }) {
  const meta = useLessonMeta()
  const future = journal.all_lessons.filter((lesson) => lesson.state === 'future' && lesson.is_live)
  const [kind, setKind] = useState<'sor' | 'soch'>('sor')
  const [lesson, setLesson] = useState(String(future[0]?.id ?? ''))
  const [number, setNumber] = useState('1')
  const [max, setMax] = useState(String(journal.course.subject.sor_max))
  const [topic, setTopic] = useState('')
  const [error, setError] = useState('')
  const submit = () => {
    if (!lesson) {
      setError(t('Будущих уроков нет'))
      return
    }
    meta.mutate(
      { lesson: Number(lesson), kind, number: Number(number) || 1, max_score: Number(max) || null, topic: topic || undefined },
      {
        onSuccess: () => {
          toast.success(t('Запланировано: ученики увидят в календаре'))
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  return (
    <Modal title={t('Запланировать СОР или СОЧ')} note={journal.course.title} onClose={onClose}>
      <Segmented
        value={kind}
        onChange={(next) => {
          setKind(next)
          setMax(String(next === 'sor' ? journal.course.subject.sor_max : journal.course.subject.soch_max))
        }}
        label={t('Вид')}
        items={[
          { value: 'sor', label: t('СОР за раздел') },
          { value: 'soch', label: t('СОЧ за четверть') },
        ]}
      />
      <Field
        kind="select"
        name="lesson"
        label={t('Урок')}
        value={lesson}
        onChange={setLesson}
        options={future.map((row) => ({ value: String(row.id), title: `${row.weekday}, ${dateWords(row.date)}, ${row.kind !== 'fo' ? t('{slot} урок · уже {kind}', { slot: row.slot, kind: row.kind_label }) : t('{slot} урок', { slot: row.slot })}` }))}
        placeholder={future.length ? undefined : t('будущих уроков нет')}
        error={error || undefined}
      />
      <Field.Row>
        <Field kind="number" name="number" label={t('Номер')} value={number} onChange={setNumber} min={1} />
        <Field kind="number" name="max" label={t('Максимум баллов')} value={max} onChange={setMax} min={1} />
      </Field.Row>
      <Field kind="text" name="topic" label={t('Раздел или тема')} value={topic} onChange={setTopic} />
      <div className="acad__actions">
        <Button onClick={submit} disabled={meta.isPending}>
          {t('Запланировать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Одна клетка сводки справа: пропуски, ФО, СОР, СОЧ, «сейчас». */
function summaryCell(stats: JournalData['rows'][number]['stats'], which: string) {
  if (which === 's-abs') {
    const marks = [stats.absent ? t('{n}н', { n: stats.absent }) : '', stats.excused ? t('{n}у', { n: stats.excused }) : '', stats.late ? t('{n}оп', { n: stats.late }) : '']
      .filter(Boolean)
      .join(' ')
    return <div className="jsum">{marks ? <b className="num">{marks}</b> : <span className="jsum__none">{t('нет')}</span>}</div>
  }
  if (which === 's-fo') return <div className="jsum">{stats.fo_avg !== null ? <b className="num">{stats.fo_avg}</b> : <span className="jsum__none">{t('нет')}</span>}</div>
  if (which === 's-sor')
    return <div className="jsum">{stats.sor_max ? <b className="num">{`${stats.sor_got}/${stats.sor_max}`}</b> : <span className="jsum__none">{t('нет')}</span>}</div>
  if (which === 's-soch')
    return <div className="jsum">{stats.soch_max ? <b className="num">{`${stats.soch_got}/${stats.soch_max}`}</b> : <span className="jsum__none">{t('впереди')}</span>}</div>
  if (which === 's-now')
    return (
      <div className="jsum">
        {stats.final !== null ? (
          <Chip tone={gradeTone(stats.final) as Tone}>{t('итог {mark}', { mark: stats.final })}</Chip>
        ) : stats.quarter_grade !== null ? (
          <>
            <Chip tone={gradeTone(stats.quarter_grade) as Tone}>{String(stats.quarter_grade)}</Chip>
            <span className="t-note num">{stats.quarter_pct} %</span>
          </>
        ) : (
          <span className="jsum__none">{t('мало оценок')}</span>
        )}
      </div>
    )
  return null
}

export default function Journal() {
  const { id } = useParams()
  const navigate = useNavigate()
  const phone = usePhone()
  const [params, setParams] = useSearchParams()
  const period = params.get('period') ?? ''
  const meta = useAcadMeta()
  const courseId = Number(id)
  const journal = useJournal(Number.isFinite(courseId) ? courseId : null, period)
  const attendance = useSaveAttendance()
  const grade = useSetGrade()
  const [mode, setMode] = useState<Mode>('both')
  const [selected, setSelected] = useState<MatrixCell | null>(null)
  const [lateAsk, setLateAsk] = useState<MatrixCell | null>(null)
  const [dialog, setDialog] = useState<'final' | 'assessment' | 'export' | null>(null)
  const { me } = useAuth()
  const mayReview = Boolean(me && homeworkReviewOpen(me.role, me.teaches))

  if (journal.isLoading && !journal.data) return <Loading kind="table" />
  if (journal.error) return <ErrorNote error={journal.error} />
  if (!journal.data) return null
  const data = journal.data
  const setPeriod = (code: string) => {
    const next = new URLSearchParams(params)
    next.set('period', code)
    setParams(next, { replace: true })
  }
  const kz = data.scheme === 'kz'
  const columns: MatrixColumn[] = data.columns.map((column) => ({
    key: column.lesson,
    title: dateShort(column.date),
    sub: column.unmarked ? t('не отмечен') : `${column.kind_label} · ${column.weekday}`,
  }))
  const summaryColumns: MatrixColumn[] = [
    { key: 's-abs', title: t('Пропуски') },
    { key: 's-fo', title: t('ФО') },
    ...(kz ? [{ key: 's-sor', title: t('СОР') }, { key: 's-soch', title: t('СОЧ') }, { key: 's-now', title: t('Сейчас') }] : []),
  ]
  const rows: MatrixRow[] = data.rows.map((row) => ({ key: row.id, title: row.full_name, sub: data.course.cohort.kind === 'stream' ? row.group : undefined }))
  // колонка «ДЗ» встаёт сразу за своим уроком; клавиатура и правка её обходят
  const hwColumns = data.homework_columns ?? []
  const hwAt = new Map(hwColumns.map((column, index) => [column.lesson, index]))
  const slots: Slot[] = []
  const matrixColumns: MatrixColumn[] = []
  data.columns.forEach((column, index) => {
    slots.push({ kind: 'lesson', index })
    matrixColumns.push(columns[index])
    const hw = hwAt.get(column.lesson)
    if (hw !== undefined) {
      slots.push({ kind: 'hw', index: hw, lesson: column.lesson })
      matrixColumns.push({ key: `hw-${column.lesson}`, title: dateShort(column.date), sub: t('ДЗ') })
    }
  })
  summaryColumns.forEach((column) => {
    slots.push({ kind: 'sum', key: String(column.key) })
    matrixColumns.push(column)
  })
  const slotOf = (key: MatrixColumn['key']) => slots[matrixColumns.findIndex((column) => column.key === key)]
  /** индекс урока в `data.columns` по колонке матрицы; «ДЗ» и сводка — null */
  const lessonAt = (col: number): number | null => {
    const slot = slots[col]
    return slot && slot.kind === 'lesson' ? slot.index : null
  }
  const onKey = (cell: MatrixCell, key: string) => {
    const at = lessonAt(cell.col)
    if (!data.may_edit || at === null) return
    const column = data.columns[at]
    const row = data.rows[cell.row]
    if (!column || !row || column.future) return
    if (column.locked) {
      toast.error(tn(data.scale.edit_days, 'Оценки старше {n} дня правит Кымбат|Оценки старше {n} дней правит Кымбат|Оценки старше {n} дней правит Кымбат'))
      return
    }
    const fail = (e: Error) => toast.error(e.message)
    const lower = key.toLowerCase()
    // буквы всех трёх языков журнала: ru «н/оп», kk «ж/к», en «A/L»
    const marks: Record<string, string> = { н: 'absent', n: 'absent', y: 'absent', ж: 'absent', a: 'absent', о: 'late', o: 'late', j: 'late', к: 'late', l: 'late', '.': 'present', б: 'present' }
    // та же граница, что у сервера: урок на замене или без учителя — объяснение, а не молчаливый отказ
    const deny = () =>
      toast.error(column.teacher ? t('Этот урок ведёт {teacher}: отметку и оценку ставит он', { teacher: column.teacher }) : t('У урока нет учителя: оценку ставит Кымбат или администратор'))
    const current = row.cells[at]
    const erase = key === 'Backspace' || key === 'Delete'
    if ((marks[lower] || (erase && current.grade === null)) && !column.may_mark) return deny()
    if ((/^[0-9]$/.test(key) || (erase && current.grade !== null)) && !column.may_grade) return deny()
    if (marks[lower] === 'late' && column.state !== 'now') {
      // прошедший урок: без времени прихода «оп» не ставится — открыть ввод времени
      setLateAsk(cell)
      setSelected(cell)
      return
    }
    if (marks[lower]) {
      // на идущем уроке время прихода — «сейчас», его ставит сервер
      attendance.mutate({ lesson: column.lesson, rows: [{ student: row.id, mark: marks[lower] }] }, { onError: fail })
      return
    }
    if (/^[0-9]$/.test(key)) {
      if (column.kind !== 'fo') {
        setSelected(cell)
        return
      }
      const value = key === '0' ? data.scale.fo_max : Number(key)
      grade.mutate({ lesson: column.lesson, student: row.id, value }, { onError: fail })
      return
    }
    if (erase) {
      if (current.grade !== null) grade.mutate({ lesson: column.lesson, student: row.id, value: null }, { onError: fail })
      else if (current.mark && current.mark !== 'present') attendance.mutate({ lesson: column.lesson, rows: [{ student: row.id, mark: 'present' }] }, { onError: fail })
    }
  }
  const selectedAt = selected ? lessonAt(selected.col) : null
  const selectedLesson = selectedAt !== null ? data.columns[selectedAt] : null
  const kpiNext = data.kpis.next_assessment

  return (
    <div>
      <ScreenHead
        title={data.course.subject.title}
        crumb={{ label: t('Журналы'), to: data.is_owner ? '/journals' : '/schedule' }}
        pills={[{ label: data.course.cohort.name, on: true }, { label: data.course.cohort.kind_title }]}
        subtitle={`${counted(data.rows.length, 'ученик|ученика|учеников')} · ${data.course.subject.scheme_title} · ${data.course.teacher?.full_name ?? ''}`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setDialog('export')}>
              {t('Выгрузить')}
            </Button>
            {data.may_edit && kz && (
              <Button variant="outline" size="sm" onClick={() => setDialog('assessment')}>
                {t('СОР или СОЧ')}
              </Button>
            )}
            {data.may_edit && kz && data.quarter && (
              <Button variant="outline" size="sm" onClick={() => setDialog('final')}>
                {t('Выставить итог')}
              </Button>
            )}
            {data.today_lesson && data.may_edit && (
              <Button size="sm" onClick={() => navigate(`/lessons/${data.today_lesson?.id}`)}>
                {t('Урок сегодня')} · {data.today_lesson.slot}
              </Button>
            )}
          </>
        }
      />
      <StatRow>
        <Kpi label={t('Уроков проведено')} value={data.kpis.held || null} none={t('ещё не было')} note={t('из {planned} за {period}', { planned: data.kpis.planned, period: data.period.title.toLowerCase() })} />
        <Kpi
          label={t('Не отмечено')}
          value={data.kpis.unmarked || null}
          none={t('всё отмечено')}
          tone={data.kpis.unmarked ? 'warn' : undefined}
          action={data.kpis.unmarked && data.kpis.first_unmarked ? { label: t('Отметить'), to: `/lessons/${data.kpis.first_unmarked}` } : undefined}
        />
        <Kpi label={t('Средний ФО')} value={data.kpis.fo_avg} none={t('оценок нет')} />
        {kz ? (
          <Kpi
            label={kpiNext ? t('Следующий {kind}', { kind: kpiNext.kind_label }) : t('Двойки сейчас')}
            value={kpiNext ? dateShort(kpiNext.date) : data.kpis.low || null}
            none={t('нет')}
            note={
              kpiNext
                ? kpiNext.max_score !== null
                  ? `${kpiNext.weekday_full}, ${tn(kpiNext.max_score, 'из {n} балла|из {n} баллов|из {n} баллов')}`
                  : kpiNext.weekday_full
                : t('по текущим оценкам')
            }
            tone={!kpiNext && data.kpis.low ? 'bad' : undefined}
          />
        ) : (
          <Kpi label={t('Учеников')} value={data.rows.length} />
        )}
      </StatRow>

      <div className="acad__toolbar">
        <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
        {!phone && (
          <Segmented
            value={mode}
            onChange={setMode}
            label={t('Что показывать')}
            items={[
              { value: 'both', label: t('Посещаемость и оценки') },
              { value: 'a', label: t('Посещаемость') },
              { value: 'g', label: t('Оценки') },
            ]}
          />
        )}
      </div>

      {phone ? (
        <DataCard title={t('Уроки')} count={data.all_lessons.length}>
          <Rows>
            {data.all_lessons.map((lesson) => (
              <Row
                key={lesson.id}
                lead={<b className="num">{Number(lesson.date.slice(8))}</b>}
                title={`${lesson.kind_label} · ${lesson.weekday}, ${dateWords(lesson.date)}`}
                note={lesson.topic || t('тема не записана')}
                right={lesson.state !== 'future' && !lesson.marked ? <Chip tone="warn">{t('не отмечен')}</Chip> : undefined}
                to={`/lessons/${lesson.id}`}
              />
            ))}
          </Rows>
        </DataCard>
      ) : data.rows.length === 0 ? (
        <DataCard title={t('Журнал')} empty={t('в составе нет учеников')} />
      ) : (
        <div className="card">
          <Matrix
            rows={rows}
            columns={matrixColumns}
            label={data.course.title}
            selected={selected}
            onSelect={setSelected}
            onKey={onKey}
            locked={(_row, column) => {
              const slot = slotOf(column.key)
              if (slot?.kind === 'hw') return false
              const found = slot?.kind === 'lesson' ? data.columns[slot.index] : undefined
              return found ? found.locked : true
            }}
            tone={(row, column) => {
              const slot = slotOf(column.key)
              const line = data.rows.find((r) => r.id === row.key)
              if (!line || !slot || slot.kind === 'sum') return undefined
              if (slot.kind === 'hw') {
                const grade = line.homework?.[slot.index]?.grade ?? null
                const tone = grade !== null ? foTone(grade, 10) : 'neutral'
                return tone
              }
              return cellTone(line.cells[slot.index], data.columns[slot.index], data.scale.fo_max)
            }}
            cell={(row, column) => {
              const line = data.rows.find((r) => r.id === row.key)
              const slot = slotOf(column.key)
              if (!line || !slot) return null
              if (slot.kind === 'lesson') return cellNode(line.cells[slot.index], data.columns[slot.index], mode)
              if (slot.kind === 'hw') return homeworkNode(line.homework?.[slot.index], mayReview ? `/homework-review/${hwColumns[slot.index].assignment}?student=${line.id}` : null)
              return summaryCell(line.stats, slot.key)
            }}
          />
          <div className="jlegend">
            <span className="jlegend__k">
              <i className="jlegend__i">·</i> {t('был')}
            </span>
            <span className="jlegend__k">
              <i className="jlegend__i jcell__a--absent">{t('н')}</i> {t('не был')}
            </span>
            <span className="jlegend__k">
              <i className="jlegend__i jcell__a--excused">{t('у')}</i> {t('уважительная')}
            </span>
            <span className="jlegend__k">
              <i className="jlegend__i jcell__a--late">{t('оп')}</i> {t('опоздал')}
            </span>
            <span className="jlegend__k">
              <i className="jlegend__i matrix__cell--unmarked" /> {t('урок не отмечен')}
            </span>
            <span className="jlegend__k">
              <Icon name="lock" size={13} /> {tn(data.scale.edit_days, 'старше {n} дня — правит Кымбат|старше {n} дней — правит Кымбат|старше {n} дней — правит Кымбат')}
            </span>
            {hwColumns.length > 0 && (
              <>
                <span className="jlegend__k">
                  <i className="jlegend__i matrix__cell--good">9</i> {t('оценка за ДЗ')}
                </span>
                <span className="jlegend__k">
                  <i className="jlegend__i jhw__chk">✓</i> {t('ДЗ проверено без оценки')}
                </span>
                <span className="jlegend__k">
                  <Chip tone="accent" size="sm">
                    {t('сдано')}
                  </Chip>{' '}
                  {mayReview ? t('ждёт проверки — нажмите, откроется работа') : t('ждёт проверки')}
                </span>
                <span className="jlegend__k">
                  <i className="jlegend__i jhw__miss">—</i> {t('ДЗ не сдано')}
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {selectedLesson && selected && selectedAt !== null && data.may_edit && !phone && <CellEditor key={`${selected.row}-${selectedAt}`} journal={data} cell={{ row: selected.row, col: selectedAt }} askLateFirst={lateAsk !== null && lateAsk.row === selected?.row && lateAsk.col === selected?.col} onClose={() => { setSelected(null); setLateAsk(null) }} />}

      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Темы уроков')} count={data.topics.length || undefined} empty={data.topics.length === 0 && t('уроков ещё не было')}>
            <Rows>
              {data.topics.map((lesson) => (
                <Row
                  key={lesson.id}
                  lead={<b className="num">{Number(lesson.date.slice(8))}</b>}
                  title={lesson.topic || t('тема не записана')}
                  note={`${lesson.weekday}, ${dateWords(lesson.date)} · ${lesson.homework ? t('дз: {homework}', { homework: lesson.homework }) : t('без домашнего задания')}`}
                  to={`/lessons/${lesson.id}`}
                />
              ))}
            </Rows>
          </DataCard>
          {selectedLesson && !data.may_edit && (
            <DataCard title={t('Выделено')}>
              <Rows>
                <Row title={data.rows[selected?.row ?? 0]?.full_name ?? ''} note={`${dateWords(selectedLesson.date)} · ${selectedLesson.kind_label}`} right={<MarkChip mark={data.rows[selected?.row ?? 0]?.cells[selectedAt ?? 0]?.mark ?? null} lateBy={data.rows[selected?.row ?? 0]?.cells[selectedAt ?? 0]?.late_by} words={meta.data?.mark_words ?? {}} />} />
              </Rows>
            </DataCard>
          )}
        </div>
      </div>

      {dialog === 'final' && <FinalDialog journal={data} onClose={() => setDialog(null)} />}
      {dialog === 'assessment' && <AssessmentDialog journal={data} onClose={() => setDialog(null)} />}
      {dialog === 'export' && (
        <ExportPreview
          path={`/acad/journals/${data.course.id}/export/?period=${encodeURIComponent(data.period.code)}`}
          fallback={t('журнал {subject} {group}.xlsx', { subject: data.course.subject.short_title, group: data.course.cohort.name })}
          title={t('Выгрузка журнала')}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}
