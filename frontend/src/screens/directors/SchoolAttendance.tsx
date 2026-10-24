/**
 * «Посещаемость» директора школы (макет BAttendance, 24.10.2026) — только
 * чтение утренних отметок кураторов. «Сегодня»: числа по школе, группы
 * плитками по параллелям, окно группы — кого нет, кто опоздал, кто освобождён.
 * «Аналитика» — те же отметки за период: по ученикам и по параллелям.
 * Виды по урокам учителей у директора школы спрятаны (решение 24.10.2026).
 */
import { useMemo, useState } from 'react'
import {
  absencesQuery,
  statsQuery,
  useAttendanceStats,
  type AttendanceStatsRow,
} from '../../api/hooks'
import { useMorning, type MorningGroup } from '../../api/directors'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import Modal from '../../components/Modal'
import { Avatar, Segmented } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { usePhone } from '../../phone'
import { todayLine } from './parts'
import './directors.css'

type Tab = 'today' | 'stats'

const STATE_WORD = { absent: tk('нет'), late: tk('опоздал'), released: tk('вне уроков') } as const
const STATE_TONE = { absent: 'bad', late: 'warn', released: 'info' } as const

export default function SchoolAttendance() {
  const [tab, setTab] = useState<Tab>('today')
  return (
    <div className="lay-screen">
      <ScreenHead title={t('Посещаемость')} subtitle={todayLine(t('утренние отметки кураторов'))} />
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'today' as const, label: t('Сегодня') },
          { value: 'stats' as const, label: t('Аналитика') },
        ]}
      />
      {tab === 'today' ? <Today /> : <Stats />}
    </div>
  )
}

function Today() {
  const { data, isLoading, error } = useMorning()
  const [parallel, setParallel] = useState('all')
  const [opened, setOpened] = useState<MorningGroup | null>(null)
  const [exporting, setExporting] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const parallels = [...new Set(data.groups.map((g) => g.parallel))].sort((a, b) => a - b)
  const shown = data.groups.filter((g) => parallel === 'all' || String(g.parallel) === parallel)
  const totals = data.totals
  const unmarked = shown.filter((g) => !g.marked)

  return (
    <>
      <div className="lay-4">
        <Kpi label={t('Нет в школе')} value={totals.absent} note={t('из {n} учеников', { n: totals.students })} />
        <Kpi label={t('Опоздали')} value={totals.late} note={t('по отметкам кураторов')} />
        <Kpi label={t('В школе')} value={totals.students - totals.absent - totals.released} note={t('с учётом опоздавших')} />
        <Kpi
          label={t('Группы отметились')}
          value={t('{marked} из {total}', { marked: totals.marked, total: totals.groups })}
          note={totals.last ? t('последняя в {time}', { time: totals.last }) : undefined}
          chip={totals.marked < totals.groups ? { label: t('не отметились: {n}', { n: totals.groups - totals.marked }), tone: 'warn' } : undefined}
        />
      </div>
      <div className="filters">
        <Segmented
          value={parallel}
          onChange={setParallel}
          label={t('Параллель')}
          items={[
            { value: 'all', label: <>{t('Все')} <span className="tabs__n num">{data.groups.length}</span></> },
            ...parallels.map((p) => ({
              value: String(p),
              label: (
                <>
                  {t('{n} классы', { n: p })} <span className="tabs__n num">{data.groups.filter((g) => g.parallel === p).length}</span>
                </>
              ),
            })),
          ]}
        />
        <span className="filters__end">
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Для СБ')}
          </Button>
        </span>
      </div>
      <DataCard
        className="card--beam"
        title={t('Утренняя отметка по группам')}
        note={unmarked.length ? t('не отметились: {names}', { names: unmarked.map((g) => g.code).join(', ') }) : undefined}
        count={shown.length}
      >
        <div className="dir__tiles">
          {shown.map((group) => (
            <button key={group.id} type="button" className="dir__tile" onClick={() => setOpened(group)}>
              <b>{group.code}</b>
              <span className="t-note">{[group.curator || t('куратор не назначен'), group.marked ? group.at : ''].filter(Boolean).join(' · ')}</span>
              <span className="dir__tilechips">
                {!group.marked ? (
                  <Chip tone="warn" size="sm">
                    {t('не отметились')}
                  </Chip>
                ) : group.absent + group.late + group.released === 0 ? (
                  <Chip tone="good" size="sm">
                    {t('все в школе')}
                  </Chip>
                ) : (
                  <>
                    {group.absent > 0 && <Chip tone="bad" size="sm">{t('нет {n}', { n: group.absent })}</Chip>}
                    {group.late > 0 && <Chip tone="warn" size="sm">{t('опоздали {n}', { n: group.late })}</Chip>}
                    {group.released > 0 && <Chip tone="info" size="sm">{t('вне уроков {n}', { n: group.released })}</Chip>}
                  </>
                )}
              </span>
            </button>
          ))}
        </div>
      </DataCard>
      {opened && (
        <Modal
          title={t('{group} · {n} класс', { group: opened.code, n: opened.parallel })}
          note={[t('Куратор {name}', { name: opened.curator || t('не назначен') }), opened.marked ? t('отмечено в {time}', { time: opened.at }) : t('не отметились')].join(' · ')}
          onClose={() => setOpened(null)}
        >
          {opened.students.length === 0 ? (
            <p className="t-note">{opened.marked ? t('Все {n} учеников в школе', { n: opened.size }) : t('Куратор ещё не отметил группу')}</p>
          ) : (
            <div className="dir__rows">
              {opened.students.map((student) => (
                <div key={student.id} className="dir__row">
                  <Avatar name={student.full_name} />
                  <span className="dir__what">
                    <b>{student.full_name}</b>
                    <span className="t-note">{student.reason || t('без комментария')}</span>
                  </span>
                  <Chip tone={STATE_TONE[student.state]} size="sm">
                    {t(STATE_WORD[student.state])}
                  </Chip>
                  <span />
                </div>
              ))}
            </div>
          )}
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setOpened(null)}>
              {t('Закрыть')}
            </Button>
          </div>
        </Modal>
      )}
      {exporting && (
        <ExportPreview
          path={`/attendance/absences/export/${absencesQuery({ from: data.date, to: data.date, group: '' })}`}
          fallback={t('отсутствующие.xlsx')}
          title={t('Для службы безопасности: по дням')}
          onClose={() => setExporting(false)}
        />
      )}
    </>
  )
}

function Stats() {
  const phone = usePhone()
  const [period, setPeriod] = useState('week')
  const { data, isLoading, error } = useAttendanceStats({ group: 'all', period })
  const morning = useMorning()
  const [exporting, setExporting] = useState(false)
  const parallelOf = useMemo(() => new Map((morning.data?.groups ?? []).map((g) => [g.code, g.parallel])), [morning.data])
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const rows = [...data.rows].filter((row) => row.absent + row.late > 0).sort((a, b) => b.absent - a.absent || b.late - a.late)
  const byParallel = new Map<number, { days: number; present: number }>()
  for (const row of data.rows) {
    const p = parallelOf.get(row.group)
    if (p === undefined || !row.days) continue
    const cell = byParallel.get(p) ?? { days: 0, present: 0 }
    cell.days += row.days
    cell.present += row.days - row.absent
    byParallel.set(p, cell)
  }

  const columns: Column<AttendanceStatsRow>[] = [
    { key: 'name', title: t('Ученик'), width: 'auto', phone: 'head', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    { key: 'group', title: t('Группа'), width: '12%', cell: (row) => <Chip size="sm">{row.group}</Chip>, sortBy: (row) => row.group },
    { key: 'present', title: t('Был'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.present}</span>, sortBy: (row) => row.present },
    { key: 'absent', title: t('Не был'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.absent}</span>, sortBy: (row) => row.absent },
    { key: 'late', title: t('Опоздал'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.late}</span>, sortBy: (row) => row.late },
    { key: 'pct', title: '%', width: '10%', align: 'right', cell: (row) => <span className="num">{row.percent ?? ''}</span>, sortBy: (row) => row.percent },
  ]

  return (
    <>
      <div className="filters">
        <Segmented value={period} onChange={setPeriod} label={t('Период')} items={data.periods.filter((p) => p.code !== 'custom').slice(0, 4).map((p) => ({ value: p.code, label: p.title }))} />
        <span className="filters__end">
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Выгрузить xlsx')}
          </Button>
        </span>
      </div>
      <div className="lay-4">
        <Kpi label={t('Средняя посещаемость')} value={data.totals.percent !== null ? `${data.totals.percent} %` : null} note={data.period.title} />
        <Kpi label={t('Отсутствий')} value={data.totals.absent} note={t('по утренним отметкам')} />
        <Kpi label={t('Опозданий')} value={data.totals.late} note={t('по утренним отметкам')} />
        <Kpi label={t('Дней отмечено')} value={data.totals.days} note={data.period.title} />
      </div>
      <div className="lay-main lay-main--even">
        <DataCard className={rows.length ? 'card--beam' : undefined} title={t('Больше всего пропусков')} note={data.period.title} count={rows.length || undefined} empty={rows.length === 0 && t('за период пропусков и опозданий нет')}>
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} limit={5} fit={!phone} />
        </DataCard>
        <div className="lay-stack">
          <DataCard title={t('По параллелям')} empty={byParallel.size === 0 && t('за период отметок не было')}>
            <div className="dir__lines">
              {[...byParallel.entries()]
                .sort((a, b) => a[0] - b[0])
                .map(([p, cell]) => (
                  <div key={p} className="dir__line">
                    <span>{t('{n} классы', { n: p })}</span>
                    <b className="num">{`${Math.round((cell.present * 100) / cell.days)} %`}</b>
                  </div>
                ))}
            </div>
          </DataCard>
        </div>
      </div>
      {exporting && (
        <ExportPreview path={`/attendance/stats/export/${statsQuery({ group: 'all', period })}`} fallback={t('посещаемость-куратора.xlsx')} title={t('Выгрузка по ученикам')} onClose={() => setExporting(false)} />
      )}
    </>
  )
}
