/**
 * Общее для экранов учебной части: неделя расписания, карточка урока в сетке,
 * переключатель периода, чип отметки, подписи дат.
 *
 * Образец — `weekView` и `lesChip` из `docs/ui/reference-src/src/screens/acad.js`:
 * на ноутбуке сетка «номер урока × день недели», на телефоне — сегменты дней
 * и список одного дня. Карточка урока — предмет, кто и кабинет, пометка
 * о замене, отмене или переносе.
 */
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Chip, type Tone } from '../../components/ui'
import { Segmented } from '../../components/patterns'
import { Button } from '../../components/ui/button'
import Icon from '../../layout/icons'
import { t } from '../../i18n'
import { usePhone } from '../../phone'
import { markTone, type AcadDay, type AcadLesson, type AcadMark, type AcadWeek } from '../../api/academics'
import './academics.css'

const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

/** «25 сентября» из `ГГГГ-ММ-ДД`. */
export function dateWords(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${Number(day)} ${t(MONTHS[Number(month) - 1])}`
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

function chipTag(lesson: AcadLesson, perspective: Perspective): string {
  if (lesson.substitute) return `${t('замена:')} ${lesson.substitute.short}`
  if (lesson.status === 'cancelled') return t('отменён')
  if (lesson.status === 'moved' && lesson.moved_from_date) return `${t('перенесён с')} ${dateShort(lesson.moved_from_date)}`
  if (lesson.cohort.kind !== 'group' && perspective !== 'teacher' && perspective !== 'edit') return lesson.cohort.short_name
  if (lesson.is_one_off && lesson.note) return lesson.note
  return ''
}

/** Карточка урока в сетке: кнопка, ведущая на урок или открывающая панель. */
export function LessonChip({
  lesson,
  perspective,
  conflict = false,
  unmarked = false,
  onOpen,
}: {
  lesson: AcadLesson
  perspective: Perspective
  conflict?: boolean
  unmarked?: boolean
  onOpen: (lesson: AcadLesson) => void
}) {
  const who =
    perspective === 'teacher'
      ? lesson.cohort.name
      : perspective === 'edit'
        ? `${lesson.actual_teacher?.short ?? ''} · ${lesson.cohort.short_name}`
        : (lesson.actual_teacher?.short ?? '')
  const tag = chipTag(lesson, perspective)
  return (
    <Button variant="ghost" className={chipClass(lesson, conflict)} onClick={() => onOpen(lesson)}>
      <span className="les__s">{lesson.subject.short_title}</span>
      <span className="les__m">
        {who}
        {lesson.room ? ` · ${lesson.room}` : ''}
      </span>
      {tag && <span className="les__tag">{tag}</span>}
      {unmarked && (
        <Chip tone="warn" size="sm">
          {t('не отмечен')}
        </Chip>
      )}
    </Button>
  )
}

/** Тень перенесённого урока на прежнем месте. */
function Ghost({ to, slot }: { to: string; slot: number }) {
  return (
    <span className="les les--off">
      <span className="les__tag">
        {t('перенесён на')} {dateShort(to)}, {slot} {t('урок')}
      </span>
    </span>
  )
}

/**
 * Неделя расписания. Сетка на ноутбуке, день на телефоне.
 *
 * `add` — редактор: пустая клетка предлагает урок, у клетки с уроком — «ещё».
 */
export function WeekGrid({
  week,
  perspective,
  onOpen,
  onAdd,
  conflictIds,
  unmarkedIds,
}: {
  week: AcadWeek
  perspective: Perspective
  onOpen: (lesson: AcadLesson) => void
  onAdd?: (date: string, slot: number) => void
  conflictIds?: number[]
  unmarkedIds?: number[]
}) {
  const phone = usePhone()
  const days = week.days.filter((day) => new Date(`${day.date}T00:00:00`).getDay() % 6 !== 0)
  const [picked, setPicked] = useState<string>(() => {
    const today = days.find((day) => day.is_today)
    return today ? today.date : (days[0]?.date ?? '')
  })
  const maxSlot = Math.max(6, ...week.lessons.map((lesson) => lesson.slot))
  const slots = week.slots.filter((slot) => slot <= Math.max(7, maxSlot))
  const conflicts = new Set(conflictIds ?? [])
  const unmarked = new Set(unmarkedIds ?? [])
  const at = (date: string, slot: number) => week.lessons.filter((lesson) => lesson.date === date && lesson.slot === slot)
  const ghostsAt = (date: string, slot: number) => week.ghosts.filter((ghost) => ghost.date === date && ghost.slot === slot)
  const isNow = (day: AcadDay, slot: number) => day.is_today && week.now_slot === slot

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
            {slots.map((slot) => {
              const here = at(day.date, slot)
              const ghosts = ghostsAt(day.date, slot)
              if (!here.length && !ghosts.length && !onAdd) return null
              return (
                <div key={slot} className={`dayl__row${isNow(day, slot) ? ' dayl__row--now' : ''}`}>
                  <div className="wk__slot">
                    <b className="num">{slot}</b>
                    <span>{week.slots.includes(slot) ? bellOf(week, slot) : ''}</span>
                  </div>
                  <div className="dayl__body">
                    {here.map((lesson) => (
                      <LessonChip
                        key={lesson.id}
                        lesson={lesson}
                        perspective={perspective}
                        conflict={conflicts.has(lesson.id)}
                        unmarked={unmarked.has(lesson.id)}
                        onOpen={onOpen}
                      />
                    ))}
                    {ghosts.map((ghost) => (
                      <Ghost key={ghost.lesson} to={ghost.moved_to_date} slot={ghost.moved_to_slot} />
                    ))}
                    {onAdd && day.school_day && (
                      <Button variant="ghost" className="wk__add" onClick={() => onAdd(day.date, slot)}>
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
    <div className="card wk__scroll">
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
                  ? `${week.lessons.filter((lesson) => lesson.date === day.date && lesson.is_live).length} ${t('ур.')}`
                  : t('не учебный')}
            </span>
          </div>
        ))}
        {slots.map((slot) => (
          <WeekRow
            key={slot}
            slot={slot}
            bell={bellOf(week, slot)}
            days={days}
            lessonsAt={at}
            ghostsAt={ghostsAt}
            isNow={isNow}
            perspective={perspective}
            conflicts={conflicts}
            unmarked={unmarked}
            onOpen={onOpen}
            onAdd={onAdd}
          />
        ))}
      </div>
    </div>
  )
}

function WeekRow({
  slot,
  bell,
  days,
  lessonsAt,
  ghostsAt,
  isNow,
  perspective,
  conflicts,
  unmarked,
  onOpen,
  onAdd,
}: {
  slot: number
  bell: string
  days: AcadDay[]
  lessonsAt: (date: string, slot: number) => AcadLesson[]
  ghostsAt: (date: string, slot: number) => AcadWeek['ghosts']
  isNow: (day: AcadDay, slot: number) => boolean
  perspective: Perspective
  conflicts: Set<number>
  unmarked: Set<number>
  onOpen: (lesson: AcadLesson) => void
  onAdd?: (date: string, slot: number) => void
}) {
  return (
    <>
      <div className="wk__slot">
        <b className="num">{slot}</b>
        <span>{bell}</span>
      </div>
      {days.map((day) => {
        const here = lessonsAt(day.date, slot)
        const ghosts = ghostsAt(day.date, slot)
        const canAdd = Boolean(onAdd) && day.school_day
        return (
          <div
            key={day.date}
            className={`wk__cell${day.is_today ? ' wk__cell--today' : ''}${isNow(day, slot) ? ' wk__cell--now' : ''}${
              day.school_day ? '' : ' wk__cell--off'
            }`}
          >
            {here.map((lesson) => (
              <LessonChip
                key={lesson.id}
                lesson={lesson}
                perspective={perspective}
                conflict={conflicts.has(lesson.id)}
                unmarked={unmarked.has(lesson.id)}
                onOpen={onOpen}
              />
            ))}
            {ghosts.map((ghost) => (
              <Ghost key={ghost.lesson} to={ghost.moved_to_date} slot={ghost.moved_to_slot} />
            ))}
            {canAdd && (
              <Button variant="ghost" className="wk__add" onClick={() => onAdd?.(day.date, slot)}>
                <Icon name="plus" size={14} />
                {here.length ? t('ещё') : t('урок')}
              </Button>
            )}
          </div>
        )
      })}
    </>
  )
}

function bellOf(week: AcadWeek, slot: number): string {
  const lesson = week.lessons.find((row) => row.slot === slot)
  return lesson ? lesson.bell.split('–')[0] : ''
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

/** Чип отметки посещаемости словами. */
export function MarkChip({ mark, words, size }: { mark: AcadMark; words: Record<string, string>; size?: 'sm' }) {
  if (mark === null) return null
  return (
    <Chip tone={markTone(mark) as Tone} size={size}>
      {t(words[mark] ?? mark)}
    </Chip>
  )
}

/** Строка «нет: Иванов А., Петров Б.» или «все были». */
export function absentWords(names: string[]): string {
  return names.length ? `${t('нет:')} ${names.join(', ')}` : t('все были')
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

/** Пояснение в карточке: абзац словами, не пустота. */
export function NoteCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card card-pad datacard">
      <header className="datacard__head">
        <span className="datacard__title t-card">{title}</span>
      </header>
      <p className="acad__note">{children}</p>
    </section>
  )
}
