/**
 * Общие куски главной ученика 8–10 и 11 (раскладка по макету).
 *
 * «Следующий урок» — главная карточка: какой урок идёт или будет следующим,
 * считается по звонкам, которые уже пришли с уроками; звонков нет — карточка
 * показывает уроки дня без «через N мин». Ниже — список «Сегодня», шапка
 * телефона и плитка даты для строк «Скоро» и «Ближайшее». Новых данных здесь
 * нет: только то, что главная уже получила.
 */
import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router'
import { shortDate } from '../../components/CalendarCard'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard } from '../../components/ui'
import { t, tn } from '../../i18n'
import { timeInSchoolZone } from '../../lib/dates'

/** Урок дня в общем виде: у 8–10 и у 11 приходят разные записи. */
export interface TodayLesson {
  key: string
  /** номер урока; у 8–10 не приходит */
  slot: number | null
  /** звонок «08:00–08:40»; пусто — звонков у группы нет */
  bell: string
  subject: string
  meta: string
  chip?: ReactNode
  to?: string
}

type Next =
  { state: 'now' | 'next'; index: number; minutes: number } | { state: 'over'; index: -1; minutes: 0 } | null

const minutesOf = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** Начало и конец звонка в минутах от полуночи; не разобрался — null. */
function bellRange(bell: string): [number, number] | null {
  const match = bell.match(/(\d{1,2}:\d{2})\D+(\d{1,2}:\d{2})/)
  return match ? [minutesOf(match[1]), minutesOf(match[2])] : null
}

/** Какой урок идёт или будет следующим — по звонкам; без звонков — по номеру с сервера. */
export function findNext(lessons: TodayLesson[], nowSlot: number | null = null): Next {
  const ranges = lessons.map((lesson) => bellRange(lesson.bell))
  if (lessons.length > 0 && ranges.every(Boolean)) {
    const now = minutesOf(timeInSchoolZone())
    for (let index = 0; index < lessons.length; index++) {
      const [start, end] = ranges[index]!
      if (now >= start && now < end) return { state: 'now', index, minutes: 0 }
      if (now < start) return { state: 'next', index, minutes: start - now }
    }
    return { state: 'over', index: -1, minutes: 0 }
  }
  const index = nowSlot === null ? -1 : lessons.findIndex((lesson) => lesson.slot === nowSlot)
  return index >= 0 ? { state: 'now', index, minutes: 0 } : null
}

const startOf = (bell: string) => bell.split(/[–-]/)[0]?.trim() ?? ''
const endOf = (bell: string) => bell.split(/[–-]/)[1]?.trim() ?? ''

/** «через 12 мин · 2 урок» / «идёт · 2 урок» / «уроки закончились». */
function nextWords(next: Next, lesson: TodayLesson | undefined): string | null {
  if (!next) return null
  if (next.state === 'over') return t('уроки закончились')
  const when =
    next.state === 'now'
      ? t('идёт')
      : next.minutes >= 60
        ? next.minutes % 60
          ? t('через {hours} ч {minutes} мин', {
              hours: Math.floor(next.minutes / 60),
              minutes: next.minutes % 60,
            })
          : t('через {hours} ч', { hours: next.minutes / 60 })
        : t('через {minutes} мин', { minutes: next.minutes })
  return lesson?.slot ? `${when} · ${t('{n} урок', { n: lesson.slot })}` : when
}

/**
 * Главная карточка с бегущим светом: следующий урок крупно, время справа;
 * под ним на ноутбуке — плитки всех уроков дня, на телефоне — полоса
 * «сколько уроков дня уже прошло».
 */
export function NextLessonCard({
  lessons,
  nowSlot = null,
  empty,
  tiles,
  className,
}: {
  lessons: TodayLesson[]
  nowSlot?: number | null
  /** фраза, когда уроков сегодня нет */
  empty: string
  /** плитки уроков дня под главным (ноутбук); без них — полоса */
  tiles: boolean
  className?: string
}) {
  const next = findNext(lessons, nowSlot)
  const lesson = next && next.index >= 0 ? lessons[next.index] : undefined
  const words = nextWords(next, lesson)
  const done = next?.state === 'over' ? lessons.length : next ? next.index : 0
  return (
    <section className={`card card-pad card--beam stuhome__next${className ? ` ${className}` : ''}`}>
      <div className="stuhome__nexthead">
        {words ? (
          <Chip tone={next?.state === 'over' ? 'neutral' : 'accent'} size="sm">
            {words}
          </Chip>
        ) : (
          <span className="datacard__title t-card">{t('Уроки сегодня')}</span>
        )}
        {lessons.length > 0 && (
          <span className="t-note">{tn(lessons.length, '{n} урок|{n} урока|{n} уроков')}</span>
        )}
      </div>
      {lessons.length === 0 ? (
        <p className="t-note">{empty}</p>
      ) : (
        lesson && (
          <div className="stuhome__nextmain">
            <div className="stuhome__nextwhat">
              <span className="stuhome__nextsubj">{lesson.subject}</span>
              {lesson.meta && <span className="t-note">{lesson.meta}</span>}
            </div>
            {lesson.bell && (
              <div className="stuhome__nextwhen">
                <span className="num stuhome__nexttime">{startOf(lesson.bell)}</span>
                <span className="t-note num">{t('до {when}', { when: endOf(lesson.bell) })}</span>
              </div>
            )}
          </div>
        )
      )}
      {/* звонков нет — главного урока не выбрать: уроки дня строками вместо плиток */}
      {lessons.length > 0 && !lesson && (
        <Rows>
          {lessons.map((item, index) => (
            <Row
              key={item.key}
              lead={<span className="num stuhome__time">{startOf(item.bell) || item.slot || index + 1}</span>}
              title={item.subject}
              note={item.meta || undefined}
              right={item.chip}
              to={item.to}
            />
          ))}
        </Rows>
      )}
      {lessons.length > 0 &&
        lesson &&
        (tiles ? (
          <div className="stuhome__tiles">
            {lessons.map((item, index) => {
              const body = (
                <>
                  <span className="num t-note">
                    {startOf(item.bell) || (item.slot ? t('{n} урок', { n: item.slot }) : '')}
                  </span>
                  <b className="stuhome__tilename">{item.subject}</b>
                  {item.meta && <span className="t-note stuhome__tilename">{item.meta}</span>}
                  {item.chip}
                </>
              )
              const cls = `stuhome__tile${lesson && index === next?.index ? ' stuhome__tile--on' : ''}`
              return item.to ? (
                <Link key={item.key} className={cls} to={item.to}>
                  {body}
                </Link>
              ) : (
                <div key={item.key} className={cls}>
                  {body}
                </div>
              )
            })}
          </div>
        ) : (
          <Bar percent={(done / lessons.length) * 100} />
        ))}
    </section>
  )
}

/** Уроки дня строками: время слева, текущий или следующий подсвечен. */
export function TodayList({
  title,
  lessons,
  nowSlot = null,
  empty,
  right,
  note,
}: {
  title: string
  lessons: TodayLesson[]
  nowSlot?: number | null
  empty: string
  right?: ReactNode
  note?: string
}) {
  const next = findNext(lessons, nowSlot)
  return (
    <DataCard
      title={title}
      count={lessons.length || undefined}
      note={note}
      empty={lessons.length === 0 && empty}
      right={right}
    >
      <Rows>
        {lessons.map((lesson, index) => (
          <Row
            key={lesson.key}
            lead={
              <span className="num stuhome__time">{startOf(lesson.bell) || lesson.slot || index + 1}</span>
            }
            title={lesson.subject}
            note={lesson.meta || undefined}
            right={lesson.chip}
            to={lesson.to}
            current={next !== null && next.index === index}
          />
        ))}
      </Rows>
    </DataCard>
  )
}

/** Плитка даты строки: число крупно, месяц под ним; сегодня — словом. */
export function DateBox({ iso, today }: { iso: string; today: string }) {
  const words = shortDate(iso, today)
  const [day, ...month] = words.split(' ')
  return (
    <span className="stuhome__date">
      {iso === today || month.length === 0 ? (
        <span className="t-note">{words}</span>
      ) : (
        <>
          <b className="num">{day}</b>
          <span className="t-note">{month.join(' ')}</span>
        </>
      )}
    </span>
  )
}

/** Шапка главной на телефоне: аватар, имя, дата и группа строкой. */
/**
 * Имя для приветствия: в учётке ФИО хранится «Фамилия Имя Отчество» —
 * имя второе слово; одно слово — оно и есть имя.
 */
export function firstNameOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean)
  return words[1] ?? words[0] ?? ''
}

/** Шапка главной на телефоне: приветствие и строка «дата · группа». Аватар — один, в полосе оболочки. */
export function PhoneHead({ title, line }: { title: string; line: string }) {
  return (
    <header className="stuhome__phonehead">
      <div className="stuhome__phonewho">
        <b className="stuhome__phonename">{title}</b>
        {line && <span className="t-note">{line}</span>}
      </div>
    </header>
  )
}

/**
 * Две колонки главной: живые карточки — каждая в своей колонке по порядку,
 * пустые одной строкой — под колонками на всю ширину, чтобы столбцы
 * кончались вровень и пустая строка не удлиняла короткий.
 */
type BoardCard = { key: string; folded: boolean; node: ReactNode }
export function Columns({ main, aside }: { main: BoardCard[]; aside: BoardCard[] }) {
  const live = (cards: BoardCard[]) => cards.filter((card) => !card.folded)
  const folded = [...main, ...aside].filter((card) => card.folded)
  return (
    <>
      <div className="lay-main">
        {[live(main), live(aside)].map((cards, index) => (
          <div key={index} className="lay-stack">
            {cards.map((card) => (
              <Fragment key={card.key}>{card.node}</Fragment>
            ))}
          </div>
        ))}
      </div>
      {folded.map((card) => (
        <Fragment key={card.key}>{card.node}</Fragment>
      ))}
    </>
  )
}
