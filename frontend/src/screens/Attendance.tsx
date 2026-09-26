/**
 * Посещаемость по урокам: группа за день и за месяц.
 *
 * Экран один на куратора, директора школы, Кымбат и администратора:
 * отметки ставят учителя на уроках, здесь их читают по группе. Куратор
 * и администратор оформляют уважительную причину за период — «н» в эти
 * дни становятся «у» во всех журналах; куратор напоминает учителю
 * о неотмеченном уроке. Право приходит с сервера (`may_excuse`, `may_remind`).
 *
 * Прежняя отметка дня закрыта: её строки остались на чтение третьим
 * видом «Отметки дня до уроков» — история, а не рабочий журнал.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useAcadAttendance,
  useRemindLesson,
  type AcadMark,
  type AttendanceDayRow,
  type AttendanceMonthRow,
} from '../api/academics'
import { useAttendanceJournal } from '../api/hooks'
import { ExportPreview } from '../components/ExportPreview'
import Field from '../components/Field'
import Matrix, { type MatrixColumn, type MatrixRow } from '../components/Matrix'
import { Row, Rows, Segmented, StatRow } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { todayAlmaty } from '../lib/dates'
import { usePhone } from '../phone'
import { ExcuseDialog } from './academics/GradesTab'
import { absentWords, dateShort, dateWords, GroupPick } from './academics/shared'
import './attendance.css'

type View = 'day' | 'month' | 'days'

/** Буква отметки в клетке: словом она в подсказке и в легенде. */
const LETTER: Record<string, string> = { absent: 'н', excused: 'у', late: 'оп', present: '·' }

function markLetter(mark: AcadMark | undefined): string {
  return mark ? t(LETTER[mark] ?? mark) : ''
}

function markToneOf(mark: AcadMark | undefined, unmarked: boolean): 'good' | 'warn' | 'bad' | 'info' | 'neutral' | undefined {
  if (mark === 'absent') return 'bad'
  if (mark === 'excused') return 'info'
  if (mark === 'late') return 'warn'
  if (mark === 'present') return 'good'
  return unmarked ? 'neutral' : undefined
}

/** Сводка месяца в клетке: «2н 1у», пусто — не пропускал. */
function monthWords(cell: { absent: number; excused: number; late: number }): string {
  return [cell.absent ? `${cell.absent}${t('н')}` : '', cell.excused ? `${cell.excused}${t('у')}` : '', cell.late ? `${cell.late}${t('оп')}` : '']
    .filter(Boolean)
    .join(' ')
}

const thisMonth = (): string => todayAlmaty().slice(0, 7)

const shiftMonth = (month: string, by: number): string => {
  const [year, number] = month.split('-').map(Number)
  const moved = new Date(year, number - 1 + by, 1)
  return `${moved.getFullYear()}-${String(moved.getMonth() + 1).padStart(2, '0')}`
}

const monthTitle = (month: string): string => {
  const [year, number] = month.split('-').map(Number)
  return new Date(year, number - 1, 1).toLocaleDateString('ru', { month: 'long', year: 'numeric' })
}

export default function Attendance() {
  // группа, вид и день живут в адресе: из карточки ученика сюда приходят
  // ссылкой на нужный день, и «Назад» возвращает ровно туда
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'month' ? 'month' : params.get('view') === 'days' ? 'days' : 'day'
  const group = params.get('group') ?? ''
  const date = params.get('date') ?? todayAlmaty()
  const month = params.get('month') ?? thisMonth()
  const set = (patch: Record<string, string>) => {
    const updated = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value) updated.set(key, value)
      else updated.delete(key)
    }
    setParams(updated, { replace: true })
  }
  const sheet = useAcadAttendance({ group, view: view === 'month' ? 'month' : 'day', date, month })
  const [exporting, setExporting] = useState(false)

  if (sheet.isLoading && !sheet.data) return <Loading kind="table" />
  if (sheet.error) return <ErrorNote error={sheet.error} />
  if (!sheet.data) return null
  const data = sheet.data
  const picked = data.group_code || group

  const switcher = (
    <div className="att__bar">
      <GroupPick groups={data.groups} value={picked} onChange={(code) => set({ group: code })} />
      <Segmented<View>
        value={view}
        onChange={(next) => set({ view: next === 'day' ? '' : next })}
        label={t('Вид')}
        items={[
          { value: 'day', label: t('День') },
          { value: 'month', label: t('Месяц') },
          { value: 'days', label: t('Отметки дня до уроков') },
        ]}
      />
    </div>
  )

  const exportPath = `/acad/attendance/export/?group=${encodeURIComponent(picked)}&view=${view === 'month' ? 'month' : 'day'}&date=${date}&month=${month}`

  return (
    <div>
      <ScreenHead
        title={t('Посещаемость')}
        subtitle={
          data.may_excuse
            ? t('Отмечают учителя на уроках. Вы оформляете уважительную причину за период и напоминаете о неотмеченных уроках.')
            : t('Отмечают учителя на уроках. Здесь посещаемость групп на чтение.')
        }
        actions={
          view !== 'days' && data.group ? (
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
          ) : undefined
        }
      />
      {switcher}
      {data.groups.length === 0 && <DataCard title={t('Групп нет')} empty={t('группы заводит администратор')} />}
      {data.groups.length > 0 && view === 'day' && <DayView data={data} date={date} onDate={(next) => set({ date: next })} />}
      {data.groups.length > 0 && view === 'month' && <MonthView data={data} month={month} onMonth={(next) => set({ month: next })} />}
      {data.groups.length > 0 && view === 'days' && <OldDays groupId={data.group} groupCode={picked} />}
      {exporting && (
        <ExportPreview
          path={exportPath}
          fallback={`посещаемость-${picked}.xlsx`}
          title={t('Выгрузка посещаемости')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}

type Sheet = NonNullable<ReturnType<typeof useAcadAttendance>['data']>

function DayView({ data, date, onDate }: { data: Sheet; date: string; onDate: (next: string) => void }) {
  const phone = usePhone()
  const navigate = useNavigate()
  const remind = useRemindLesson()
  const [excusing, setExcusing] = useState<{ student: number; from: string; to: string } | null>(null)
  const rows = data.rows as AttendanceDayRow[]
  const slots = data.slots ?? []
  const unmarked = data.unmarked ?? []
  const allDay = data.all_day ?? []
  const notExcused = data.not_excused ?? []
  const totals = data.totals ?? { absent: 0, excused: 0, late: 0 }
  const fail = (e: Error) => toast.error(e.message)
  const byId = new Map(rows.map((row) => [row.id, row]))
  const slotIndex = new Map(slots.map((slot, index) => [slot.slot, index]))
  const matrixRows: MatrixRow[] = rows.map((row) => ({ key: row.id, title: row.full_name }))
  const columns: MatrixColumn[] = slots.map((slot) => ({ key: slot.slot, title: `${slot.slot} ${t('ур.')}`, sub: slot.subjects.join(' / ') }))
  const cellOf = (row: MatrixRow, column: MatrixColumn) => byId.get(Number(row.key))?.cells[slotIndex.get(Number(column.key)) ?? -1]
  const rowWords = (row: AttendanceDayRow) => {
    const parts = row.cells
      .filter((cell) => cell.has_lesson && cell.mark && cell.mark !== 'present')
      .map((cell) => `${cell.subject} ${markLetter(cell.mark)}`)
    if (parts.length) return parts.join(', ')
    return row.marked ? t('все уроки был') : t('уроки ещё не отмечены')
  }
  const remindAll = () => {
    for (const lesson of unmarked) remind.mutate(lesson.id, { onError: fail })
    toast.success(`${t('Напоминания ушли:')} ${counted(unmarked.length, ['учитель', 'учителя', 'учителей'])}`)
  }

  return (
    <>
      <div className="att__bar">
        <Field kind="date" name="date" label={t('День')} value={date} max={todayAlmaty()} onChange={onDate} className="att__date" />
        {date !== todayAlmaty() && (
          <Button variant="link" size="sm" onClick={() => onDate(todayAlmaty())}>
            {t('К сегодня')}
          </Button>
        )}
        <span className="t-note">{data.date_words}</span>
      </div>
      <StatRow>
        <Kpi label={t('Уроков')} value={slots.length || null} none={data.school_day ? t('уроков нет') : t('не учебный')} note={data.now_slot ? `${t('идёт')} ${data.now_slot} ${t('урок')}` : undefined} />
        <Kpi label={t('Не было')} value={totals.absent || null} none={t('нет')} tone={totals.absent ? 'bad' : undefined} note={data.absent_now?.length ? absentWords(data.absent_now) : t('по урокам с отметкой')} />
        <Kpi label={t('По уважительной')} value={totals.excused || null} none={t('нет')} />
        <Kpi label={t('Опоздали')} value={totals.late || null} none={t('нет')} tone={totals.late ? 'warn' : undefined} />
        <Kpi
          label={t('Не отмечено')}
          value={unmarked.length || null}
          none={slots.length ? t('всё отмечено') : t('нет')}
          tone={unmarked.length ? 'warn' : undefined}
          action={unmarked.length && data.may_remind ? { label: t('Напомнить всем'), onClick: remindAll } : undefined}
        />
      </StatRow>

      <DataCard title={data.group_code} count={rows.length || undefined} empty={rows.length === 0 && t('в группе нет учеников')} note={slots.length === 0 && rows.length ? t('в этот день уроков нет') : undefined}>
        {rows.length > 0 && slots.length > 0 && !phone && (
          <>
            <Matrix
              rows={matrixRows}
              columns={columns}
              label={t('Посещаемость по урокам')}
              rowHead={t('Ученик')}
              locked={(row, column) => !cellOf(row, column)?.has_lesson}
              tone={(row, column) => {
                const cell = cellOf(row, column)
                return cell?.has_lesson ? markToneOf(cell.mark, Boolean(cell.unmarked)) : undefined
              }}
              cell={(row, column) => {
                const cell = cellOf(row, column)
                if (!cell?.has_lesson) return null
                if (cell.unmarked) return <span className="att__cellnote">{t('не отмечен')}</span>
                if (!cell.started) return <span className="att__cellnote">{t('впереди')}</span>
                return <b className={`att__mark att__mark--${cell.mark ?? 'none'}`}>{markLetter(cell.mark)}</b>
              }}
            />
            <p className="t-note att__legend">{t('«·» — был, «н» — не был, «у» — уважительная причина, «оп» — опоздал.')}</p>
          </>
        )}
        {rows.length > 0 && slots.length > 0 && phone && (
          <Rows>
            {rows.map((row) => (
              <Row key={row.id} avatar={row.full_name} title={row.full_name} note={rowWords(row)} tone={row.absent ? 'bad' : row.late ? 'warn' : 'good'} to={`/students/${row.id}?tab=grades`} />
            ))}
          </Rows>
        )}
      </DataCard>

      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Не отмечено учителями')} count={unmarked.length || undefined} empty={unmarked.length === 0 && (slots.length ? t('все отметили') : t('уроков не было'))}>
            <Rows>
              {unmarked.map((lesson) => (
                <Row
                  key={lesson.id}
                  icon="alert"
                  tone="warn"
                  title={`${lesson.slot} ${t('урок')} · ${lesson.subject.short_title} · ${lesson.actual_teacher?.short ?? ''}`}
                  note={`${lesson.bell} · ${lesson.cohort.short_name}`}
                  acts={
                    <>
                      {data.may_remind && (
                        <Button variant="secondary" size="sm" onClick={() => remind.mutate(lesson.id, { onSuccess: (r) => toast.success(`${t('Напоминание ушло:')} ${r.reminded}`), onError: fail })}>
                          {t('Напомнить')}
                        </Button>
                      )}
                      <Button variant="outline" size="sm" onClick={() => navigate(`/lessons/${lesson.id}`)}>
                        {t('Открыть')}
                      </Button>
                    </>
                  }
                />
              ))}
            </Rows>
          </DataCard>
          <DataCard title={t('Отсутствуют весь день')} count={allDay.length || undefined} empty={allDay.length === 0 && t('таких нет')}>
            <Rows>
              {allDay.map((row) => (
                <Row
                  key={row.id}
                  avatar={row.full_name}
                  title={row.full_name}
                  note={row.excused ? t('уважительная причина оформлена') : t('причина не оформлена')}
                  right={<Chip tone={row.excused ? 'info' : 'bad'}>{row.excused ? t('у') : t('н')}</Chip>}
                  acts={
                    data.may_excuse && !row.excused ? (
                      <Button variant="secondary" size="sm" onClick={() => setExcusing({ student: row.id, from: date, to: date })}>
                        {t('Оформить')}
                      </Button>
                    ) : undefined
                  }
                />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Дни без причины в этом месяце')} count={notExcused.length || undefined} empty={notExcused.length === 0 && t('таких нет')} note={t('не меньше двух «н» и большей части уроков дня')}>
            <Rows>
              {notExcused.map((row) => (
                <Row
                  key={row.id}
                  avatar={row.full_name}
                  tone="bad"
                  title={row.full_name}
                  note={row.days.map((day) => dateShort(day)).join(', ')}
                  acts={
                    data.may_excuse ? (
                      <Button variant="secondary" size="sm" onClick={() => setExcusing({ student: row.id, from: row.days[0], to: row.days[row.days.length - 1] })}>
                        {t('Оформить')}
                      </Button>
                    ) : undefined
                  }
                  to={data.may_excuse ? undefined : `/students/${row.id}?tab=grades`}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
      {excusing && <ExcuseDialog student={excusing.student} from={excusing.from} to={excusing.to} onClose={() => setExcusing(null)} />}
    </>
  )
}

function MonthView({ data, month, onMonth }: { data: Sheet; month: string; onMonth: (next: string) => void }) {
  const phone = usePhone()
  const [excusing, setExcusing] = useState<{ student: number; from: string; to: string } | null>(null)
  const rows = data.rows as AttendanceMonthRow[]
  const days = data.days ?? []
  const byId = new Map(rows.map((row) => [row.id, row]))
  const dayIndex = new Map(days.map((day, index) => [day.date, index]))
  const matrixRows: MatrixRow[] = rows.map((row) => ({ key: row.id, title: row.full_name }))
  const columns: MatrixColumn[] = [
    ...days.map((day) => ({ key: day.date, title: String(day.day), sub: day.weekday })),
    { key: 's-pct', title: t('Посещ.'), sub: '%' },
    { key: 's-abs', title: t('Пропуски'), sub: t('н / у / оп') },
  ]
  const totalAbsent = rows.reduce((sum, row) => sum + row.absent, 0)
  const totalExcused = rows.reduce((sum, row) => sum + row.excused, 0)
  const totalLate = rows.reduce((sum, row) => sum + row.late, 0)
  const withPct = rows.filter((row) => row.pct !== null)
  const avgPct = withPct.length ? Math.round(withPct.reduce((sum, row) => sum + (row.pct ?? 0), 0) / withPct.length) : null
  const unexcused = rows.filter((row) => row.unexcused_days.length)

  return (
    <>
      <div className="att__bar">
        <div className="wknav__group">
          <Button variant="outline" size="sm" aria-label={t('Предыдущий месяц')} onClick={() => onMonth(shiftMonth(month, -1))}>
            {t('Раньше')}
          </Button>
          <span className="wknav__title" aria-live="polite">
            {data.month_title || monthTitle(month)}
          </span>
          <Button variant="outline" size="sm" aria-label={t('Следующий месяц')} disabled={month >= thisMonth()} onClick={() => onMonth(shiftMonth(month, 1))}>
            {t('Позже')}
          </Button>
        </div>
      </div>
      <StatRow>
        <Kpi label={t('Посещаемость')} value={avgPct !== null ? `${avgPct} %` : null} none={t('уроков с отметкой не было')} note={t('по урокам с отметкой')} />
        <Kpi label={t('Не было')} value={totalAbsent || null} none={t('нет')} tone={totalAbsent ? 'bad' : undefined} />
        <Kpi label={t('По уважительной')} value={totalExcused || null} none={t('нет')} />
        <Kpi label={t('Опоздали')} value={totalLate || null} none={t('нет')} tone={totalLate ? 'warn' : undefined} />
        <Kpi label={t('Дни без причины')} value={unexcused.length || null} none={t('нет')} tone={unexcused.length ? 'bad' : undefined} note={unexcused.length ? t('учеников') : undefined} />
      </StatRow>
      <DataCard title={data.group_code} count={rows.length || undefined} empty={rows.length === 0 && t('в группе нет учеников')} note={days.length === 0 && rows.length ? t('учебных дней в этом месяце ещё не было') : undefined}>
        {rows.length > 0 && days.length > 0 && !phone && (
          <Matrix
            rows={matrixRows}
            columns={columns}
            label={t('Посещаемость за месяц')}
            rowHead={t('Ученик')}
            locked={(row, column) => {
              const line = byId.get(Number(row.key))
              const index = dayIndex.get(String(column.key))
              return index === undefined ? false : (line?.cells[index]?.lessons ?? 0) === 0
            }}
            tone={(row, column) => {
              const line = byId.get(Number(row.key))
              if (!line) return undefined
              if (column.key === 's-pct') return line.pct !== null && line.pct < 85 ? 'bad' : undefined
              const cell = line.cells[dayIndex.get(String(column.key)) ?? -1]
              if (!cell || !cell.lessons) return undefined
              if (cell.absent) return 'bad'
              if (cell.excused) return 'info'
              if (cell.late) return 'warn'
              if (cell.unmarked) return 'neutral'
              return undefined
            }}
            cell={(row, column) => {
              const line = byId.get(Number(row.key))
              if (!line) return null
              if (column.key === 's-pct') return <b className="num">{line.pct === null ? t('нет') : `${line.pct} %`}</b>
              if (column.key === 's-abs') return <b className="num">{monthWords(line) || t('нет')}</b>
              const cell = line.cells[dayIndex.get(String(column.key)) ?? -1]
              if (!cell || !cell.lessons) return null
              const words = monthWords(cell)
              return words ? <b className="num">{words}</b> : <span className="att__dot">{'·'}</span>
            }}
          />
        )}
        {rows.length > 0 && days.length > 0 && phone && (
          <Rows>
            {rows.map((row) => (
              <Row
                key={row.id}
                avatar={row.full_name}
                title={row.full_name}
                note={monthWords(row) || t('пропусков нет')}
                value={row.pct === null ? null : `${row.pct} %`}
                none={t('нет')}
                tone={row.pct !== null && row.pct < 85 ? 'bad' : 'good'}
                to={`/students/${row.id}?tab=grades`}
              />
            ))}
          </Rows>
        )}
      </DataCard>
      <DataCard title={t('Дни без причины')} count={unexcused.length || undefined} empty={unexcused.length === 0 && t('таких нет')}>
        <Rows>
          {unexcused.map((row) => (
            <Row
              key={row.id}
              avatar={row.full_name}
              tone="bad"
              title={row.full_name}
              note={row.unexcused_days.map((day) => dateWords(day)).join(', ')}
              acts={
                data.may_excuse ? (
                  <Button variant="secondary" size="sm" onClick={() => setExcusing({ student: row.id, from: row.unexcused_days[0], to: row.unexcused_days[row.unexcused_days.length - 1] })}>
                    {t('Оформить')}
                  </Button>
                ) : undefined
              }
            />
          ))}
        </Rows>
      </DataCard>
      {excusing && <ExcuseDialog student={excusing.student} from={excusing.from} to={excusing.to} onClose={() => setExcusing(null)} />}
    </>
  )
}

/** Прежние отметки дня — история до перехода на уроки, только чтение. */
function OldDays({ groupId, groupCode }: { groupId: number | null; groupCode: string }) {
  const phone = usePhone()
  const [month, setMonth] = useState(thisMonth())
  const journal = useAttendanceJournal(groupId ? String(groupId) : '', month, false, groupId !== null)
  if (journal.isLoading && !journal.data) return <Loading kind="table" />
  if (journal.error) return <ErrorNote error={journal.error} />
  const data = journal.data
  if (!data) return null
  const marked = data.rows.filter((row) => row.marked > 0)
  const columns: MatrixColumn[] = [
    ...data.days.map((day) => ({ key: day.date, title: String(day.day), sub: day.weekday })),
    { key: 's-sum', title: t('Итог') },
  ]
  const byId = new Map(data.rows.map((row) => [row.student, row]))
  const dayIndex = new Map(data.days.map((day, index) => [day.date, index]))
  return (
    <>
      <div className="att__bar">
        <div className="wknav__group">
          <Button variant="outline" size="sm" onClick={() => setMonth(shiftMonth(month, -1))}>
            {t('Раньше')}
          </Button>
          <span className="wknav__title">{monthTitle(month)}</span>
          <Button variant="outline" size="sm" disabled={month >= thisMonth()} onClick={() => setMonth(shiftMonth(month, 1))}>
            {t('Позже')}
          </Button>
        </div>
        <span className="t-note">{t('Отметка дня закрыта: посещаемость ведётся по урокам. Прежние отметки остались на чтение.')}</span>
      </div>
      <DataCard title={`${groupCode} · ${t('отметки дня')}`} count={marked.length || undefined} empty={marked.length === 0 && t('отметок дня за этот месяц не было')}>
        {marked.length > 0 && !phone && (
          <Matrix
            rows={marked.map((row) => ({ key: row.student, title: row.full_name }))}
            columns={columns}
            label={t('Прежние отметки дня')}
            rowHead={t('Ученик')}
            locked={(_row, column) => column.key !== 's-sum' && !data.days[dayIndex.get(String(column.key)) ?? -1]?.school_day}
            tone={(row, column) => {
              const cell = byId.get(Number(row.key))?.cells[dayIndex.get(String(column.key)) ?? -1]
              return cell === 'absent' ? 'bad' : cell === 'present' ? 'good' : undefined
            }}
            cell={(row, column) => {
              const line = byId.get(Number(row.key))
              if (!line) return null
              if (column.key === 's-sum') return <b className="num">{line.summary}</b>
              const cell = line.cells[dayIndex.get(String(column.key)) ?? -1]
              if (cell === 'absent') return <b className="att__mark att__mark--absent">{t('н')}</b>
              if (cell === 'present') return <span className="att__dot">{'·'}</span>
              return null
            }}
          />
        )}
        {marked.length > 0 && phone && (
          <Rows>
            {marked.map((row) => (
              <Row key={row.student} avatar={row.full_name} title={row.full_name} value={row.summary} tone={row.absent ? 'bad' : 'good'} />
            ))}
          </Rows>
        )}
      </DataCard>
    </>
  )
}

export type { Tone }
