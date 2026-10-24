/**
 * «Отчёты» — одно место у директора школы и академического директора
 * (макеты BReports и EReports, 24.10.2026). Отчёты собирает сервер из того,
 * что уже есть: утренние отметки, СБ, отчёты родителям, звонки, посещаемость
 * по урокам; у Кымбат — успеваемость по параллелям, учителя, Mock Test.
 * «Открыть» — окно с цифрами, «Скачать» — xlsx, «Просмотрено» — отметка.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  reportExportPath,
  useReportGroups,
  useSchoolReport,
  useSchoolReports,
  type ReportArchiveRow,
  type ReportGroupRow,
  type ReportTopic,
  type SchoolReport,
} from '../../api/directors'
import { useAuth } from '../../auth/AuthContext'
import DataTable, { type Column } from '../../components/DataTable'
import { Segmented } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, ScreenTabs, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { usePhone } from '../../phone'
import { formatDate } from '../../lib/format'
import { Mono, monoOf, ReportDialog, SeenChip, todayLine } from './parts'
import { StaffTaskDialog } from './StaffTasks'

const TOPICS: Record<ReportTopic, string> = {
  attendance: tk('Посещаемость'),
  parents: tk('Отчёты родителям'),
  calls: tk('Звонки'),
  grades: tk('Успеваемость'),
  teachers: tk('Учителя'),
  exams: tk('Экзамены'),
}

const STATE_TONE: Record<ReportGroupRow['state'], Tone> = { none: 'neutral', built: 'warn', checked: 'info', sent: 'good' }

/** Период строкой: день, неделя с понедельника или месяц. */
function periodWords(period: string): string {
  if (/^\d{4}-\d{2}$/.test(period)) return period.split('-').reverse().join('.')
  return /^\d{4}-\d{2}-\d{2}$/.test(period) ? formatDate(period) : period
}

function useDownload() {
  const [busy, setBusy] = useState(false)
  return {
    busy,
    run: (kind: string, period: string, name: string) => {
      setBusy(true)
      downloadFile(reportExportPath(kind, period), `${name}.xlsx`)
        .then(() => toast.success(t('Файл xlsx скачан')))
        .catch((reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason)))
        .finally(() => setBusy(false))
    },
  }
}

export default function SchoolReports() {
  const { me } = useAuth()
  const phone = usePhone()
  const navigate = useNavigate()
  const exam = me?.role === 'director_exam'
  const { data, isLoading, error } = useSchoolReports()
  const groups = useReportGroups()
  const teachers = useSchoolReport(exam ? 'teachers' : null)
  const [topic, setTopic] = useState<'all' | ReportTopic>('all')
  const [state, setState] = useState<'all' | ReportGroupRow['state']>('all')
  const [opened, setOpened] = useState<{ kind: string; period?: string } | null>(null)
  const [tasking, setTasking] = useState<{ id: number; name: string } | null>(null)
  const download = useDownload()

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const fresh = data.current.filter((row) => !row.seen)
  const all: (ReportArchiveRow & { summary?: string })[] = [...data.current, ...data.archive]
  const topics = [...new Set(all.map((row) => row.topic))]
  const shown = all.filter((row) => topic === 'all' || row.topic === topic)
  const groupRows = groups.data?.rows ?? []
  const pickedGroups = groupRows.filter((row) => state === 'all' || row.state === state)
  const checked = groupRows.filter((row) => row.state === 'checked' || row.state === 'sent').length
  const teacherRows = (teachers.data as (SchoolReport & { teachers?: { teacher_id: number; teacher: string; subjects: string; lessons: number; homework: number }[] }) | undefined)?.teachers ?? []

  const columns: Column<ReportArchiveRow & { summary?: string }>[] = [
    {
      key: 'title',
      title: t('Отчёт'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <span className="personcell">
          <Mono>{monoOf(row.title)}</Mono>
          <span className="personcell__text">
            <b>{row.title}</b>
            <span className="t-note">{row.source}</span>
          </span>
        </span>
      ),
    },
    { key: 'period', title: t('Дата'), width: '120px', cell: (row) => periodWords(row.period) },
    { key: 'state', title: t('Статус'), width: '130px', cell: (row) => <SeenChip seen={row.seen} /> },
    {
      key: 'acts',
      title: '',
      width: '200px',
      actions: true,
      cell: (row) => (
        <>
          <Button variant="ghost" size="sm" disabled={download.busy} onClick={() => download.run(row.kind, row.period, row.title)}>
            {t('Скачать')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setOpened({ kind: row.kind, period: row.period })}>
            {t('Открыть')}
          </Button>
        </>
      ),
    },
  ]

  const groupColumns: Column<ReportGroupRow>[] = [
    { key: 'group', title: t('Группа'), width: '120px', phone: 'head', cell: (row) => <b>{row.group}</b> },
    { key: 'curator', title: t('Куратор'), width: 'auto', cell: (row) => row.curator || t('не назначен') },
    { key: 'students', title: t('Учеников'), width: '100px', align: 'right', cell: (row) => <span className="num">{row.students}</span> },
    { key: 'state', title: t('Статус'), width: '170px', cell: (row) => <Chip tone={STATE_TONE[row.state]} size="sm">{row.state_title}</Chip> },
    {
      key: 'acts',
      title: '',
      width: '120px',
      actions: true,
      cell: (row) => (
        <Button variant="outline" size="sm" onClick={() => navigate(`/reports?group=${encodeURIComponent(row.group)}`)}>
          {t('Открыть')}
        </Button>
      ),
    },
  ]

  const teacherColumns: Column<{ teacher_id: number; teacher: string; subjects: string; lessons: number; homework: number }>[] = [
    { key: 'teacher', title: t('Учитель'), width: 'auto', phone: 'head', cell: (row) => <b>{row.teacher}</b> },
    { key: 'subjects', title: t('Предмет'), width: 'auto', cell: (row) => row.subjects },
    { key: 'lessons', title: t('Уроков не отмечено'), width: '150px', align: 'right', cell: (row) => <span className="num">{row.lessons}</span> },
    { key: 'homework', title: t('ДЗ не проверено'), width: '140px', align: 'right', cell: (row) => <span className="num">{row.homework}</span> },
    {
      key: 'acts',
      title: '',
      width: '170px',
      actions: true,
      cell: (row) => (
        <Button variant="outline" size="sm" onClick={() => setTasking({ id: row.teacher_id, name: row.teacher })}>
          {t('Поставить задачу')}
        </Button>
      ),
    },
  ]

  const lessons = teacherRows.reduce((sum, row) => sum + row.lessons, 0)
  const homework = teacherRows.reduce((sum, row) => sum + row.homework, 0)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Отчёты')}
        subtitle={todayLine(exam ? t('успеваемость, учителя, экзамены, родители') : t('посещаемость, СБ, родители и звонки'))}
      />
      {exam && (
        <div className="lay-4">
          <Kpi label={t('Новых отчётов')} value={fresh.length} note={t('за неделю')} />
          <Kpi label={t('Уроков не отмечено')} value={lessons} note={t('у {n} учителей', { n: teacherRows.filter((row) => row.lessons).length })} />
          <Kpi label={t('ДЗ не проверено')} value={homework} note={t('работ за неделю')} />
          <Kpi label={t('Отчёты родителям проверены')} value={t('{n} из {total}', { n: checked, total: groupRows.length })} note={t('групп за месяц')} />
        </div>
      )}
      <DataCard
        className="card--beam"
        title={t('Новые отчёты')}
        count={fresh.length || undefined}
        empty={fresh.length === 0 && t('новых отчётов нет — всё просмотрено')}
      >
        <div className="dir__rows">
          {fresh.map((report) => (
            <div key={report.kind} className="dir__row">
              <Mono>{monoOf(report.title)}</Mono>
              <span className="dir__what">
                <b>{report.title}</b>
                <span className="t-note">{[report.source, report.summary].filter(Boolean).join(' · ')}</span>
              </span>
              <SeenChip seen={false} />
              <span className="dir__acts">
                <Button variant="ghost" size="sm" disabled={download.busy} onClick={() => download.run(report.kind, report.period, report.title)}>
                  {t('Скачать')}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setOpened({ kind: report.kind })}>
                  {t('Открыть')}
                </Button>
              </span>
            </div>
          ))}
        </div>
      </DataCard>
      <ScreenTabs
        value={topic}
        onChange={setTopic}
        items={[
          { value: 'all' as const, label: <>{t('Все')} <span className="tabs__n num">{all.length}</span></> },
          ...topics.map((code) => ({
            value: code,
            label: (
              <>
                {t(TOPICS[code])} <span className="tabs__n num">{all.filter((row) => row.topic === code).length}</span>
              </>
            ),
          })),
        ]}
      />
      <DataCard title={topic === 'all' ? t('Все отчёты') : t(TOPICS[topic])} count={shown.length}>
        <DataTable columns={columns} rows={shown} rowKey={(row) => `${row.kind}-${row.period}`} limit={5} fit={!phone} />
      </DataCard>
      {exam && teacherRows.length > 0 && (
        <DataCard title={t('Отчёт учителей за неделю')} note={teachers.data?.source} count={teacherRows.length}>
          <DataTable columns={teacherColumns} rows={teacherRows} rowKey={(row) => row.teacher_id} limit={5} fit={!phone} />
        </DataCard>
      )}
      <DataCard
        title={groups.data ? t('Отчёты родителям за {month}', { month: periodWords(groups.data.month) }) : t('Отчёты родителям')}
        count={groupRows.length || undefined}
        empty={groupRows.length === 0 && t('групп нет')}
      >
        <div className="filters">
          <Segmented
            value={state}
            onChange={setState}
            label={t('Статус отчётов')}
            items={(['all', 'checked', 'built', 'none', 'sent'] as const).map((code) => ({
              value: code,
              label: (
                <>
                  {code === 'all' ? t('Все') : t(STATE_WORDS[code])}
                  <span className="tabs__n num">{code === 'all' ? groupRows.length : groupRows.filter((row) => row.state === code).length}</span>
                </>
              ),
            }))}
          />
        </div>
        <DataTable columns={groupColumns} rows={pickedGroups} rowKey={(row) => row.group_id} limit={5} fit={!phone} empty={t('с таким статусом групп нет')} />
      </DataCard>
      {opened && <ReportDialog kind={opened.kind} period={opened.period} onClose={() => setOpened(null)} />}
      {tasking && <StaffTaskDialog assignee={tasking} onClose={() => setTasking(null)} />}
    </div>
  )
}

const STATE_WORDS: Record<ReportGroupRow['state'], string> = {
  none: tk('Не собраны'),
  built: tk('Собраны'),
  checked: tk('Проверены'),
  sent: tk('Отправлены'),
}
