/**
 * «Посещаемость» куратора (решение владельца, 19.10.2026): первым открывается
 * лист отметки за сегодня, сверху вкладки по группам, рядом — аналитика.
 *
 * Отметка — в школе, нет или опоздал, без минут: строка как в составе урока
 * у учителя — ФИО и три кнопки, нажатие сохраняется сразу; у «нет» и «опоздал» —
 * короткий комментарий в строке.
 * С отметками учителей это не связано (правило 19.10): в процент по урокам не идёт.
 * Виды по урокам у куратора спрятаны переключателем `CURATOR_HIDDEN.lessonAttendance`.
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  absencesQuery,
  statsQuery,
  useAttendanceSheet,
  useAttendanceStats,
  useMarkAttendance,
  type AttendanceRow,
  type AttendanceStatsRow,
  type DayMark,
} from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import { ExportPreview } from '../components/ExportPreview'
import Field from '../components/Field'
import Modal from '../components/Modal'
import { Avatar, Row, Rows, Segmented, StatRow } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { t, tk, tn } from '../i18n'
import { todayAlmaty } from '../lib/dates'
import { formatDate, formatTime } from '../lib/format'
import { usePhone } from '../phone'
import { ALL, useGroup, useMyGroups } from './curator/state'
import { dateWords } from './academics/shared'
import GroupSwitch from './curator/GroupSwitch'
import './attendance.css'
import './curator/curator-layout.css'

type Tab = 'mark' | 'stats'

const MARK_WORDS: Record<DayMark, string> = { present: tk('в школе'), absent: tk('нет'), late: tk('опоздал') }
const MARK_TONE: Record<DayMark, Tone> = { present: 'good', absent: 'bad', late: 'warn' }

// --- Отметка -------------------------------------------------------------------------

/** Строка ученика — как в составе урока у учителя: ФИО и три кнопки рядом (решение владельца, 19.10.2026). */
function MarkRow({ group, row, onSaved }: { group: number; row: AttendanceRow; onSaved: (result: { noted: { by: string; at: string } | null; absent: number; late_count: number }) => void }) {
  const save = useMarkAttendance()
  const [mark, setMark] = useState<DayMark>(row.mark)
  const [reason, setReason] = useState(row.reason)
  const [saved, setSaved] = useState(false)
  const timer = useRef<number | null>(null)
  useEffect(() => {
    setMark(row.mark)
    setReason(row.reason)
  }, [row.mark, row.reason])

  const send = (nextMark: DayMark, nextReason: string) =>
    save.mutate(
      { group, student: row.student, mark: nextMark, reason: nextReason },
      {
        onSuccess: (result) => {
          setSaved(true)
          onSaved(result)
        },
        onError: (error) => {
          setMark(row.mark)
          setReason(row.reason)
          toast.error(error.message)
        },
      },
    )
  const pick = (next: DayMark) => {
    if (next === mark) return
    setMark(next)
    setSaved(false)
    send(next, next === 'present' ? '' : reason)
  }
  const comment = (value: string) => {
    setReason(value)
    setSaved(false)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => send(mark, value.trim()), 600)
  }

  return (
    <div className="cmark__row">
      <div className="cmark__who">
        <div className="cmark__name">{row.full_name}</div>
        {saved && !save.isPending && <div className="cmark__note">{t('сохранено')}</div>}
      </div>
      <div className="cmark__att">
        <Segmented<DayMark>
          usageFilter={false}
          value={mark}
          onChange={pick}
          label={t('{name}: отметка', { name: row.full_name })}
          items={[
            { value: 'present', label: t(MARK_WORDS.present) },
            { value: 'absent', label: t(MARK_WORDS.absent) },
            { value: 'late', label: t(MARK_WORDS.late) },
          ]}
        />
      </div>
      <div className="cmark__comment">
        {mark !== 'present' && (
          <Input
            value={reason}
            placeholder={t('Комментарий, если знаете причину')}
            aria-label={t('{name}: комментарий', { name: row.full_name })}
            maxLength={200}
            onChange={(event) => comment(event.target.value)}
          />
        )}
      </div>
    </div>
  )
}

function GroupSheet({ groupId, groupCode, lead = false }: { groupId: number; groupCode: string; lead?: boolean }) {
  const today = todayAlmaty()
  const sheet = useAttendanceSheet(String(groupId), today, true)
  const [summary, setSummary] = useState<{ noted: { by: string; at: string } | null; absent: number; late_count: number } | null>(null)
  if (sheet.isLoading && !sheet.data) return <Loading kind="table" />
  if (sheet.error) return <ErrorNote error={sheet.error} />
  const data = sheet.data
  if (!data) return null
  const noted = summary?.noted ?? data.noted
  const absent = summary?.absent ?? data.absent
  const late = summary?.late_count ?? data.late_count
  const note = [
    noted ? t('отметил {who} в {time}', { who: noted.by, time: formatTime(noted.at) }) : '',
    absent ? tn(absent, 'нет {n}|нет {n}|нет {n}') : '',
    late ? tn(late, 'опоздал {n}|опоздали {n}|опоздали {n}') : '',
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <DataCard
      className={lead ? 'card--beam' : undefined}
      title={`${groupCode} · ${dateWords(today)}`}
      note={note || undefined}
      count={data.rows.length || undefined}
      empty={data.rows.length === 0 && t('в группе нет учеников')}
    >
      <div className="cmark">
        {data.rows.map((row) => (
          <MarkRow key={row.student} group={data.group} row={row} onSaved={setSummary} />
        ))}
      </div>
    </DataCard>
  )
}

// --- Аналитика ----------------------------------------------------------------------

function StudentDates({ row, words, onClose }: { row: AttendanceStatsRow; words: Record<DayMark, string>; onClose: () => void }) {
  return (
    <Modal title={row.full_name} note={`${row.group} · ${t('не был {absent}, опоздал {late}', { absent: row.absent, late: row.late })}`} onClose={onClose}>
      <Rows>
        {row.dates.map((day) => (
          <Row
            key={`${day.date}-${day.mark}`}
            icon="clock"
            tone={MARK_TONE[day.mark]}
            title={formatDate(day.date)}
            note={day.reason || undefined}
            right={<Chip tone={MARK_TONE[day.mark]} size="sm">{words[day.mark]}</Chip>}
          />
        ))}
      </Rows>
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
    </Modal>
  )
}

function Stats({ group }: { group: string }) {
  const phone = usePhone()
  const [period, setPeriod] = useState('week')
  const [from, setFrom] = useState(`${todayAlmaty().slice(0, 7)}-01`)
  const [to, setTo] = useState(todayAlmaty())
  const [opened, setOpened] = useState<number | null>(null)
  const [exporting, setExporting] = useState<'table' | 'security' | null>(null)
  const params = { group, period, from, to }
  const stats = useAttendanceStats(params)
  if (stats.isLoading && !stats.data) return <Loading kind="table" />
  if (stats.error) return <ErrorNote error={stats.error} />
  const data = stats.data
  if (!data) return null
  const all = group === ALL
  // по умолчанию — кто чаще не был, потом кто чаще опаздывал; колонки сортируются и сами
  const rows = [...data.rows].sort((a, b) => b.absent - a.absent || b.late - a.late || a.full_name.localeCompare(b.full_name))
  const columns: Column<AttendanceStatsRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <span className="personcell">
          <Avatar name={row.full_name} size={30} />
          <b>{row.full_name}</b>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    ...(all ? [{ key: 'group', title: t('Группа'), width: '12%', cell: (row: AttendanceStatsRow) => <Chip size="sm">{row.group}</Chip>, sortBy: (row: AttendanceStatsRow) => row.group }] : []),
    { key: 'present', title: t('Был'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.present}</span>, sortBy: (row) => row.present },
    { key: 'absent', title: t('Не был'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.absent}</span>, sortBy: (row) => row.absent },
    { key: 'late', title: t('Опоздал'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.late}</span>, sortBy: (row) => row.late },
    {
      key: 'percent',
      title: t('Процент'),
      width: '16%',
      align: 'right',
      // процент числом и полосой из того же числа
      cell: (row) =>
        row.percent === null ? (
          <span className="t-note">{t('нет')}</span>
        ) : (
          <span className="catt__pct">
            <span className="cstudents__bar" aria-hidden="true">
              <i style={{ width: `${row.percent}%` }} />
            </span>
            <b className="num">{row.percent} %</b>
          </span>
        ),
      sortBy: (row) => row.percent,
    },
  ]
  const current = opened === null ? null : data.rows.find((row) => row.id === opened) ?? null
  return (
    <>
      <div className="filters">
        <Segmented value={period} onChange={setPeriod} label={t('Период')} items={data.periods.map((row) => ({ value: row.code, label: t(row.title) }))} />
        {period === 'custom' ? (
          <>
            <Field usageFilter kind="date" name="from" label={t('С')} value={from} max={to} onChange={setFrom} className="att__date" />
            <Field usageFilter kind="date" name="to" label={t('По')} value={to} max={todayAlmaty()} onChange={setTo} className="att__date" />
          </>
        ) : (
          <span className="t-note num">{`${formatDate(data.period.from)} — ${formatDate(data.period.to)}`}</span>
        )}
        {rows.length > 0 && (
          <span className="filters__end catt__exports">
            <Button variant="outline" size="sm" onClick={() => setExporting('table')}>
              {t('Выгрузить')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setExporting('security')}>
              {t('Для СБ')}
            </Button>
          </span>
        )}
      </div>
      <StatRow>
        <Kpi label={t('Средний процент')} value={data.totals.percent === null ? null : `${data.totals.percent} %`} none={t('нет')} note={rows.length ? tn(rows.length, 'по {n} ученику|по {n} ученикам|по {n} ученикам') : undefined} />
        <Kpi label={t('Дней отмечено')} value={data.totals.days || null} none={t('нет')} />
        <Kpi label={t('Отсутствий')} value={data.totals.absent || null} none={t('нет')} note={t('за период')} />
        <Kpi label={t('Опозданий')} value={data.totals.late || null} none={t('нет')} note={t('за период')} />
      </StatRow>
      <DataCard className={rows.length ? 'card--beam' : undefined} title={t('По ученикам')} count={rows.length || undefined} empty={rows.length === 0 && t('за период отметок не было')}>
        {rows.length > 0 && <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => setOpened(row.id)} fit={!phone} />}
      </DataCard>
      {current && <StudentDates row={current} words={data.words} onClose={() => setOpened(null)} />}
      {exporting === 'table' && (
        <ExportPreview path={`/attendance/stats/export/${statsQuery(params)}`} fallback={t('посещаемость-куратора.xlsx')} title={t('Выгрузка по ученикам')} onClose={() => setExporting(null)} />
      )}
      {exporting === 'security' && (
        <ExportPreview
          path={`/attendance/absences/export/${absencesQuery({ from: data.period.from, to: data.period.to, group: all ? '' : group })}`}
          fallback={t('отсутствующие.xlsx')}
          title={t('Для службы безопасности: по дням')}
          onClose={() => setExporting(null)}
        />
      )}
    </>
  )
}

// --- Экран --------------------------------------------------------------------------

export default function CuratorAttendance() {
  const phone = usePhone()
  const [params, setParams] = useSearchParams()
  const [group, setGroup] = useGroup()
  const { groups, ready } = useMyGroups()
  const tab: Tab = params.get('tab') === 'stats' ? 'stats' : 'mark'
  const setTab = (next: Tab) => {
    const copy = new URLSearchParams(params)
    if (next === 'mark') copy.delete('tab')
    else copy.set('tab', next)
    setParams(copy, { replace: true })
  }
  if (!ready) return <Loading kind="table" />
  const shown = group === ALL ? groups : groups.filter((row) => row.code === group)
  const modes = (
    <Segmented<Tab>
      value={tab}
      onChange={setTab}
      label={t('Раздел')}
      items={[
        { value: 'mark', label: t('Отметка') },
        { value: 'stats', label: t('Аналитика') },
      ]}
    />
  )
  return (
    <div className="lay-screen catt">
      {/* «Отметка / Аналитика» — справа в шапке; на телефоне шапка прячет действия
          в меню, поэтому там переключатель — своей строкой под группами */}
      <ScreenHead title={t('Посещаемость')} subtitle={t('Утренняя отметка по своим группам и аналитика за период')} actions={!phone && groups.length > 0 ? modes : undefined} />
      {groups.length === 0 ? (
        <DataCard title={t('Вам не назначены группы')} empty={t('Обратитесь к администратору: группы куратору назначает он.')} />
      ) : (
        <>
          <GroupSwitch groups={groups} value={group} onChange={setGroup} />
          {phone && <div className="att__bar">{modes}</div>}
          {tab === 'mark' && (
            <div className={shown.length > 1 ? 'lay-2 catt__sheets' : 'catt__sheets'}>
              {shown.map((row, index) => (
                <GroupSheet key={row.id} groupId={row.id} groupCode={row.code} lead={index === 0} />
              ))}
            </div>
          )}
          {tab === 'stats' && <Stats group={group} />}
        </>
      )}
    </div>
  )
}
