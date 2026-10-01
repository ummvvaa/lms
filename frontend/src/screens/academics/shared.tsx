/**
 * Общее для экранов учебной части: неделя расписания, карточка урока в сетке,
 * переключатель периода, чип отметки, подписи дат.
 *
 * Образец — `weekView` и `lesChip` из `docs/ui/reference.html`:
 * на ноутбуке сетка «номер урока × день недели», на телефоне — сегменты дней
 * и список одного дня. Карточка урока — предмет, кто и кабинет, пометка
 * о замене, отмене или переносе.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Chip, type Tone } from '../../components/ui'
import Field from '../../components/Field'
import { Segmented } from '../../components/patterns'
import { Button } from '../../components/ui/button'
import Icon from '../../layout/icons'
import { t, tk, tn } from '../../i18n'
import { usePhone } from '../../phone'
import { toast } from 'sonner'
import { markTone, useSetGrade, type AcadDay, type AcadLesson, type AcadMark, type AcadWeek, type AcadWeekRow } from '../../api/academics'
import { timeInSchoolZone } from '../../lib/dates'
import { formatDayMonth } from '../../lib/format'
import './academics.css'

/** «25 сентября» из `ГГГГ-ММ-ДД`. */
export function dateWords(iso: string): string {
  return formatDayMonth(iso.slice(0, 10))
}

/** «25.09». */
export function dateShort(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${day}.${month}`
}

/** «25.09.2026». */
export function dateFull(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}.${month}.${year}`
}

/** Понедельник недели, в которую входит день. */
/** Неделя расписания живёт в адресе (`?from=`): ссылка из дайджеста, письма
 *  или сценария открывает нужную неделю, а не текущую. Пусто — текущая. */
export function useWeekStart(): [string, (date: string) => void] {
  const [params, setParams] = useSearchParams()
  const start = params.get('from') ?? ''
  const setStart = (date: string) => {
    const next = new URLSearchParams(params)
    if (date) next.set('from', date)
    else next.delete('from')
    setParams(next, { replace: true })
  }
  return [start, setStart]
}

export function weekStart(iso: string): string {
  const day = new Date(`${iso}T00:00:00`)
  const shift = (day.getDay() + 6) % 7
  day.setDate(day.getDate() - shift)
  return day.toISOString().slice(0, 10)
}

export function addDays(iso: string, days: number): string {
  const day = new Date(`${iso}T00:00:00`)
  day.setDate(day.getDate() + days)
  return day.toISOString().slice(0, 10)
}

/** Кто учится, одним словом для сетки: состав или учитель. */
export type Perspective = 'teacher' | 'group' | 'student' | 'edit'

function chipClass(lesson: AcadLesson, conflict: boolean): string {
  const kind = lesson.cohort.kind
  const sub = kind === 'subgroup' ? (lesson.cohort.number === 1 ? ' les--sub1' : ' les--sub2') : kind === 'stream' ? ' les--stream' : ''
  const changed = lesson.substitute || lesson.status === 'moved' ? ' les--changed' : ''
  const off = lesson.status === 'cancelled' ? ' les--off' : ''
  return `les${sub}${changed}${off}${conflict ? ' les--conflict' : ''}`
}

function chipTag(lesson: AcadLesson): string {
  if (lesson.substitute) return t('замена: {teacher}', { teacher: lesson.substitute.short })
  if (lesson.status === 'cancelled') return t('отменён')
  if (lesson.status === 'moved' && lesson.moved_from_date) return t('перенесён с {date}', { date: dateShort(lesson.moved_from_date) })
  if (lesson.is_one_off && lesson.note) return lesson.note
  return ''
}

/** Уроков в клетке на виду; остальные раскрываются словом «ещё N». */
const MAX_IN_CELL = 2

/**
 * Карточка урока в сетке: отдельный блок с отступом — предмет, ниже
 * учитель · кабинет · состав (решение владельца, 27.09.2026). Один вид
 * у ученика, учителя и куратора; у учителя своё имя не пишется.
 */
export function LessonChip({
  lesson,
  perspective,
  conflict = false,
  unmarked = false,
  number = false,
  onOpen,
}: {
  lesson: AcadLesson
  perspective: Perspective
  conflict?: boolean
  unmarked?: boolean
  /** номер урока в карточке: ряд недели — время, а сеток звонков на экране несколько */
  number?: boolean
  onOpen: (lesson: AcadLesson) => void
}) {
  const meta = [
    number ? t('{n} ур.', { n: lesson.slot }) : '',
    perspective === 'teacher' ? '' : (lesson.actual_teacher?.short ?? t('учитель не назначен')),
    lesson.room,
    lesson.cohort.kind === 'group' && perspective === 'group' ? '' : lesson.cohort.short_name,
  ].filter(Boolean)
  const tag = chipTag(lesson)
  return (
    <Button variant="ghost" className={chipClass(lesson, conflict)} onClick={() => onOpen(lesson)}>
      <span className="les__s">{lesson.subject.title}</span>
      {meta.length > 0 && <span className="les__m">{meta.join(' · ')}</span>}
      {tag && <span className="les__tag">{tag}</span>}
      {unmarked && (
        <Chip tone="warn" size="sm">
          {t('не отмечен')}
        </Chip>
      )}
    </Button>
  )
}

/** Ряд недели, в который встаёт урок или тень: время начала, без звонка — номер. */
function rowOf(starts: string, slot: number): string {
  return starts || `#${slot}`
}

/**
 * Подпись ряда. Одна сетка звонков на экране — номер урока и время начала,
 * как привыкли; несколько (неделя учителя, кабинета) — время начала и конца:
 * в 10:15 идёт 4 урок у 8–9 и 1 урок у 10–11, номер тогда — у урока.
 */
function RowLabel({ row, mixed }: { row: AcadWeekRow; mixed: boolean }) {
  if (!row.starts || (!mixed && row.slot !== null))
    return (
      <div className="wk__slot">
        <b className="num">{row.slot}</b>
        <span className="num">{row.starts}</span>
      </div>
    )
  return (
    <div className="wk__slot wk__slot--time">
      <b className="num">{row.starts}</b>
      <span className="num">{row.ends}</span>
    </div>
  )
}

/** Тень перенесённого урока на прежнем месте. */
function Ghost({ to, slot }: { to: string; slot: number }) {
  return (
    <span className="les les--off">
      <span className="les__tag">
        {t('перенесён на {date}, {slot} урок', { date: dateShort(to), slot })}
      </span>
    </span>
  )
}

/** Содержимое клетки: до двух уроков, тени и «ещё N», раскрывающее остальное. */
function CellLessons({
  cellKey,
  lessons,
  ghosts,
  expanded,
  onToggle,
  perspective,
  conflicts,
  unmarked,
  number,
  onOpen,
}: {
  cellKey: string
  lessons: AcadLesson[]
  ghosts: AcadWeek['ghosts']
  expanded: Set<string>
  onToggle: (key: string) => void
  perspective: Perspective
  conflicts: Set<number>
  unmarked: Set<number>
  number: boolean
  onOpen: (lesson: AcadLesson) => void
}) {
  const open = expanded.has(cellKey)
  const shown = open ? lessons : lessons.slice(0, MAX_IN_CELL)
  const rest = lessons.length - shown.length
  return (
    <>
      {shown.map((lesson) => (
        <LessonChip
          key={lesson.id}
          lesson={lesson}
          perspective={perspective}
          conflict={conflicts.has(lesson.id)}
          unmarked={unmarked.has(lesson.id)}
          number={number}
          onOpen={onOpen}
        />
      ))}
      {ghosts.map((ghost) => (
        <Ghost key={ghost.lesson} to={ghost.moved_to_date} slot={ghost.moved_to_slot} />
      ))}
      {rest > 0 && (
        <Button variant="link" size="sm" className="wk__more" onClick={() => onToggle(cellKey)}>
          {t('ещё {count}', { count: rest })}
        </Button>
      )}
      {open && lessons.length > MAX_IN_CELL && (
        <Button variant="link" size="sm" className="wk__more" onClick={() => onToggle(cellKey)}>
          {t('свернуть')}
        </Button>
      )}
    </>
  )
}

/**
 * Неделя расписания. Сетка на ноутбуке, день на телефоне.
 *
 * Ряд — время начала урока по звонкам его группы, а не номер урока
 * (решение владельца, 01.10.2026): у 8–9 первый урок в 8:00, у 10–11 —
 * в 10:15, по номеру они вставали в один ряд. Ряды собирает сервер
 * (`week.rows`) по тем же звонкам, что проверка накладок.
 *
 * Клетка растёт по содержимому: уроки — отдельные блоки друг под другом,
 * больше двух — два и «ещё N». `add` — редактор: пустая клетка предлагает
 * урок, у клетки с уроком — «ещё».
 */
export function WeekGrid({
  week,
  perspective,
  onOpen,
  onAdd,
  conflictIds,
  unmarkedIds,
  fill = false,
}: {
  week: AcadWeek
  perspective: Perspective
  onOpen: (lesson: AcadLesson) => void
  onAdd?: (date: string, row: AcadWeekRow) => void
  conflictIds?: number[]
  unmarkedIds?: number[]
  /** неделя на всю высоту окна: ряды уроков тянутся до низа экрана */
  fill?: boolean
}) {
  const phone = usePhone()
  const days = week.days.filter((day) => new Date(`${day.date}T00:00:00`).getDay() % 6 !== 0)
  const [picked, setPicked] = useState<string>(() => {
    const today = days.find((day) => day.is_today)
    return today ? today.date : (days[0]?.date ?? '')
  })
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const toggle = (key: string) =>
    setExpanded((old) => {
      const next = new Set(old)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const rows = week.rows
  const conflicts = new Set(conflictIds ?? [])
  const unmarked = new Set(unmarkedIds ?? [])
  const at = (date: string, key: string) => week.lessons.filter((lesson) => lesson.date === date && rowOf(lesson.starts, lesson.slot) === key)
  const ghostsAt = (date: string, key: string) => week.ghosts.filter((ghost) => ghost.date === date && rowOf(ghost.starts, ghost.slot) === key)
  // «сейчас» — по звонкам группы каждого урока
  const isNow = (day: AcadDay, key: string) => day.is_today && at(day.date, key).some((lesson) => lesson.state === 'now')

  if (phone) {
    const day = days.find((row) => row.date === picked) ?? days[0]
    if (!day) return null
    return (
      <div>
        <Segmented
          value={day.date}
          onChange={setPicked}
          label={t('День недели')}
          items={days.map((row) => ({ value: row.date, label: `${row.weekday} ${Number(row.date.slice(8))}` }))}
        />
        <div className="card card-pad">
          <div className="dayl">
            {rows.map((row) => {
              const here = at(day.date, row.key)
              const ghosts = ghostsAt(day.date, row.key)
              if (!here.length && !ghosts.length && !onAdd) return null
              return (
                <div key={row.key} className={`dayl__row${isNow(day, row.key) ? ' dayl__row--now' : ''}`}>
                  <RowLabel row={row} mixed={week.mixed} />
                  <div className="dayl__body">
                    <CellLessons
                      cellKey={`${day.date}-${row.key}`}
                      lessons={here}
                      ghosts={ghosts}
                      expanded={expanded}
                      onToggle={toggle}
                      perspective={perspective}
                      conflicts={conflicts}
                      unmarked={unmarked}
                      number={week.mixed}
                      onOpen={onOpen}
                    />
                    {onAdd && day.school_day && (
                      <Button variant="ghost" className="wk__add" onClick={() => onAdd(day.date, row)}>
                        <Icon name="plus" size={14} />
                        {here.length ? t('ещё урок') : t('добавить урок')}
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`card wk__scroll${fill ? ' wk__scroll--fill' : ''}`}>
      <div className="wk">
        <div className="wk__head" />
        {days.map((day) => (
          <div key={day.date} className={`wk__head${day.is_today ? ' wk__head--today' : ''}`}>
            <span>
              {day.weekday}, {dateWords(day.date)}
            </span>
            <span className="wk__headnote">
              {day.is_today
                ? t('сегодня')
                : day.school_day
                  ? tn(week.lessons.filter((lesson) => lesson.date === day.date && lesson.is_live).length, '{n} ур.|{n} ур.|{n} ур.')
                  : t('не учебный')}
            </span>
          </div>
        ))}
        {rows.map((row) => (
          <WeekRow
            key={row.key}
            row={row}
            mixed={week.mixed}
            days={days}
            lessonsAt={at}
            ghostsAt={ghostsAt}
            isNow={isNow}
            perspective={perspective}
            conflicts={conflicts}
            unmarked={unmarked}
            expanded={expanded}
            onToggle={toggle}
            onOpen={onOpen}
            onAdd={onAdd}
          />
        ))}
      </div>
    </div>
  )
}

function WeekRow({
  row,
  mixed,
  days,
  lessonsAt,
  ghostsAt,
  isNow,
  perspective,
  conflicts,
  unmarked,
  expanded,
  onToggle,
  onOpen,
  onAdd,
}: {
  row: AcadWeekRow
  mixed: boolean
  days: AcadDay[]
  lessonsAt: (date: string, key: string) => AcadLesson[]
  ghostsAt: (date: string, key: string) => AcadWeek['ghosts']
  isNow: (day: AcadDay, key: string) => boolean
  perspective: Perspective
  conflicts: Set<number>
  unmarked: Set<number>
  expanded: Set<string>
  onToggle: (key: string) => void
  onOpen: (lesson: AcadLesson) => void
  onAdd?: (date: string, row: AcadWeekRow) => void
}) {
  return (
    <>
      <RowLabel row={row} mixed={mixed} />
      {days.map((day) => {
        const here = lessonsAt(day.date, row.key)
        const ghosts = ghostsAt(day.date, row.key)
        const canAdd = Boolean(onAdd) && day.school_day
        return (
          <div
            key={day.date}
            className={`wk__cell${day.is_today ? ' wk__cell--today' : ''}${isNow(day, row.key) ? ' wk__cell--now' : ''}${
              day.school_day ? '' : ' wk__cell--off'
            }`}
          >
            <CellLessons
              cellKey={`${day.date}-${row.key}`}
              lessons={here}
              ghosts={ghosts}
              expanded={expanded}
              onToggle={onToggle}
              perspective={perspective}
              conflicts={conflicts}
              unmarked={unmarked}
              number={mixed}
              onOpen={onOpen}
            />
            {canAdd && (
              <Button variant="ghost" size="icon-sm" className="wk__add" aria-label={t('Добавить урок')} title={t('Добавить урок')} onClick={() => onAdd?.(day.date, row)}>
                <Icon name="plus" size={14} />
              </Button>
            )}
          </div>
        )
      })}
    </>
  )
}

/** Стрелки недели и «К сегодня». */
export function WeekNav({ start, today, onChange }: { start: string; today: string; onChange: (start: string) => void }) {
  const end = addDays(start, 4)
  return (
    <div className="wknav__group">
      <Button variant="outline" size="icon-sm" aria-label={t('Прошлая неделя')} onClick={() => onChange(addDays(start, -7))}>
        <Icon name="chevronLeft" size={15} />
      </Button>
      <span className="wknav__title">
        {Number(start.slice(8))}–{dateWords(end)}
      </span>
      <Button variant="outline" size="icon-sm" aria-label={t('Следующая неделя')} onClick={() => onChange(addDays(start, 7))}>
        <Icon name="chevronRight" size={15} />
      </Button>
      {weekStart(today) !== start && (
        <Button variant="link" size="sm" onClick={() => onChange(weekStart(today))}>
          {t('К сегодня')}
        </Button>
      )}
    </div>
  )
}

/** Переключатель периода: неделя, месяц, четверти года. */
export function PeriodSwitch({
  value,
  periods,
  onChange,
}: {
  value: string
  periods: { code: string; title: string }[]
  onChange: (code: string) => void
}) {
  return (
    <Segmented value={value} onChange={onChange} label={t('Период')} items={periods.map((row) => ({ value: row.code, label: t(row.title) }))} />
  )
}

/** Под числом опозданий: «всего 25 мин», у старых — «ещё 2 без времени». */
export function lateTotal(attendance: { late: number; late_minutes?: number; late_unknown?: number }): string | undefined {
  if (!attendance.late) return undefined
  const known = attendance.late - (attendance.late_unknown ?? 0)
  const parts = [known ? t('всего {minutes} мин', { minutes: attendance.late_minutes ?? 0 }) : '', attendance.late_unknown ? t('без времени: {count}', { count: attendance.late_unknown }) : '']
  return parts.filter(Boolean).join(' · ')
}

/** «опоздал на 12 мин» или, у опозданий без времени, «опоздал · время не указано». */
export function lateWords(lateBy: number | null | undefined): string {
  return lateBy === null || lateBy === undefined ? t('опоздал · время не указано') : t('опоздал на {minutes} мин', { minutes: lateBy })
}

/** Чип отметки посещаемости словами; у опоздания — на сколько минут. */
export function MarkChip({ mark, words, size, lateBy }: { mark: AcadMark; words: Record<string, string>; size?: 'sm'; lateBy?: number | null }) {
  if (mark === null) return null
  return (
    <Chip tone={markTone(mark) as Tone} size={size}>
      {mark === 'late' ? lateWords(lateBy) : t(words[mark] ?? mark)}
    </Chip>
  )
}

/**
 * «Пришёл в»: время прихода опоздавшего. На идущем уроке подставлено «сейчас»
 * по Алматы, на прошедшем — пусто и обязательно. Проверку по звонкам делает
 * сервер: к началу урока — это «Был», после конца — «Не был».
 */
export function ArrivalForm({
  state,
  arrived,
  busy,
  onSubmit,
  onCancel,
}: {
  state: AcadLesson['state']
  arrived?: string | null
  busy?: boolean
  onSubmit: (time: string) => void
  onCancel?: () => void
}) {
  const [time, setTime] = useState(arrived ?? (state === 'now' ? timeInSchoolZone() : ''))
  return (
    <div className="arrival">
      <Field kind="time" name="arrived" label={t('Пришёл в')} value={time} onChange={setTime} required autoFocus />
      <div className="acad__actions">
        <Button size="sm" disabled={busy || !/^\d{1,2}:\d{2}$/.test(time)} onClick={() => onSubmit(time)}>
          {t('Отметить опоздание')}
        </Button>
        {onCancel && (
          <Button variant="outline" size="sm" onClick={onCancel}>
            {t('Отмена')}
          </Button>
        )}
      </div>
    </div>
  )
}

/** Строка «нет: Иванов А., Петров Б.» или «все были». */
export function absentWords(names: string[]): string {
  return names.length ? t('нет: {names}', { names: names.join(', ') }) : t('все были')
}

/** Кнопка, ведущая на экран урока: у учителя — отметка, у остальных — просмотр. */
export function OpenLesson({ lesson, label, primary = false }: { lesson: AcadLesson; label?: string; primary?: boolean }) {
  const navigate = useNavigate()
  return (
    <Button variant={primary ? 'default' : 'outline'} size="sm" onClick={() => navigate(`/lessons/${lesson.id}`)}>
      {label ?? t('Открыть')}
    </Button>
  )
}

/**
 * Выбор группы на экране, общем для ролей с разным числом групп: куратору
 * две-три — сегменты, Салтанат и Кымбат одиннадцать — список.
 */
export function GroupPick({
  groups,
  value,
  onChange,
  all,
}: {
  groups: { id: number; code: string }[]
  value: string
  onChange: (code: string) => void
  /** подпись пункта «все группы»; без неё выбирается только одна */
  all?: string
}) {
  const items = [...(all ? [{ value: 'all', label: all }] : []), ...groups.map((group) => ({ value: group.code, label: group.code }))]
  if (groups.length === 0) return null
  if (groups.length === 1 && !all)
    return (
      <p className="acad__pick t-note">
        {t('Группа')} <b>{groups[0].code}</b>
      </p>
    )
  if (items.length <= 5) return <Segmented value={value} onChange={onChange} label={t('Группа')} items={items} />
  return (
    <Field
      kind="select"
      name="group"
      label={t('Группа')}
      value={value}
      onChange={onChange}
      className="acad__pick"
      options={items.map((item) => ({ value: item.value, title: item.label }))}
    />
  )
}


/** Предел комментария к оценке — как у `Grade.comment` на сервере. */
export const GRADE_COMMENT_MAX = 300

/** Подсказка у поля комментария: кто его увидит. */
export const GRADE_COMMENT_HINT = tk('Видит ученик. Попадёт в отчёт родителям')

/**
 * Оценка и комментарий к ней — одна запись (`Grade`), один запрос.
 *
 * Оценка уходит на сервер сразу при выборе, вместе с уже набранным
 * комментарием. Комментарий, дописанный после оценки, — кнопкой
 * «Сохранить» или Enter, и тоже вместе с оценкой. Недописанный
 * комментарий при уходе с экрана или к другой клетке не теряется:
 * он сохраняется сам, если оценка есть.
 */
export function useGradeComment({ lesson, student, value: current, comment }: { lesson: number; student: number; value: number | null; comment: string }) {
  const mutation = useSetGrade()
  const [draft, setDraft] = useState(comment)
  // сохранённый на сервере текст сменился — поле показывает его
  useEffect(() => setDraft(comment), [comment, lesson, student])
  const dirty = draft.trim() !== comment.trim()
  const fail = (e: Error) => toast.error(e.message)
  const put = (value: number | null, text = draft) =>
    mutation.mutate({ lesson, student, value, comment: value === null ? '' : text.trim().slice(0, GRADE_COMMENT_MAX) }, { onError: fail })
  // недописанное сохраняется при уходе: последние значения — в ref, а не в замыкании
  const latest = useRef({ dirty, current, draft, lesson, student })
  latest.current = { dirty, current, draft, lesson, student }
  const { mutate } = mutation
  useEffect(
    () => () => {
      const last = latest.current
      if (last.dirty && last.current !== null) mutate({ lesson: last.lesson, student: last.student, value: last.current, comment: last.draft.trim().slice(0, GRADE_COMMENT_MAX) })
    },
    // экземпляр живёт на одной клетке: у журнала панель пересоздаётся ключом клетки
    [mutate],
  )
  return {
    draft,
    setDraft: (text: string) => setDraft(text.slice(0, GRADE_COMMENT_MAX)),
    dirty,
    busy: mutation.isPending,
    /** поставить или сменить оценку — с набранным комментарием */
    putValue: (value: number | null) => put(value),
    /** сохранить комментарий к стоящей оценке */
    saveComment: () => {
      if (current !== null) put(current)
    },
  }
}
