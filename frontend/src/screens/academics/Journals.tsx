/**
 * Журналы учителя списком: ученики, уроки, средний ФО, СОР.
 */
import { useNavigate } from 'react-router'
import { useTeacherJournals, type TeacherJournals } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { namesLine } from '../../components/patterns'
import { Bar, Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, withNumbers } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { dateWords } from './shared'

type JournalRow = TeacherJournals['rows'][number]

export default function Journals() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useTeacherJournals()
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (data.rows.length === 0)
    return (
      <div className="lay-screen">
        <ScreenHead title={t('Журналы')} />
        <DataCard title={t('Журналов нет')} empty={t('журнал появится, когда вас поставят в расписание')} />
      </div>
    )

  const columns: Column<JournalRow>[] = [
    {
      key: 'title',
      title: t('Журнал'),
      width: '26%',
      cell: (row) => (
        <span>
          <b>{row.subject.title}</b>
          <br />
          <span className="t-note">
            {row.cohort.name} · {row.cohort.kind_title}
          </span>
        </span>
      ),
      sortBy: (row) => row.subject.title,
    },
    { key: 'students', title: t('Учеников'), width: '10%', align: 'right', cell: (row) => <b className="num">{row.students}</b>, sortBy: (row) => row.students },
    {
      key: 'held',
      title: t('Уроков'),
      width: '16%',
      align: 'right',
      cell: (row) => (
        <span className="jlist__held num">
          <span>{withNumbers(t('{done} из {total}', { total: row.planned }), { done: row.held })}</span>
          <Bar percent={row.planned ? (row.held / row.planned) * 100 : 0} />
        </span>
      ),
      sortBy: (row) => row.held,
    },
    { key: 'fo', title: t('Средний ФО'), width: '12%', align: 'right', cell: (row) => (row.fo_avg === null ? <span className="t-note">{t('оценок нет')}</span> : <b className="num">{row.fo_avg}</b>), sortBy: (row) => row.fo_avg },
    {
      key: 'sor',
      title: t('СОР'),
      width: '10%',
      align: 'right',
      cell: (row) =>
        row.subject.scheme !== 'kz' ? (
          <span className="t-note">{t('не пишут')}</span>
        ) : (
          <span className="num">
            {withNumbers(t('{done} из {total}', { total: row.sor_all }), { done: row.sor_done })}
          </span>
        ),
    },
    {
      key: 'state',
      title: '',
      width: '16%',
      cell: (row) => (row.unmarked > 0 ? <Chip tone="warn">{tn(row.unmarked, '{n} не отмечен|{n} не отмечено|{n} не отмечено')}</Chip> : <Chip tone="good">{t('всё отмечено')}</Chip>),
    },
    {
      key: 'open',
      title: '',
      width: '10%',
      align: 'right',
      cell: (row) => (
        <Button variant="secondary" size="sm" onClick={() => navigate(`/journals/${row.id}`)}>
          {t('Открыть')}
        </Button>
      ),
    },
  ]

  const students = data.rows.reduce((sum, row) => sum + row.students, 0)
  const unmarked = data.rows.filter((row) => row.unmarked > 0)
  const unmarkedTotal = unmarked.reduce((sum, row) => sum + row.unmarked, 0)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Журналы')}
        subtitle={[data.teacher.full_name, counted(data.rows.length, 'журнал|журнала|журналов'), ...(data.quarter ? [t('{quarter} до {date}', { quarter: data.quarter.title, date: dateWords(data.quarter.ends) })] : [])].join(' · ')}
      />
      {/* показатели — из уже пришедших строк: сумма учеников и неотмеченных уроков */}
      <div className="lay-3">
        <Kpi label={t('Конец четверти')} value={data.quarter ? dateWords(data.quarter.ends) : null} none={t('каникулы')} note={data.quarter?.title ?? ''} />
        <Kpi label={t('Учеников')} value={students} note={counted(data.rows.length, 'журнал|журнала|журналов')} />
        <Kpi
          label={t('Не отмечено')}
          value={unmarkedTotal || null}
          none={t('всё отмечено')}
          tone={unmarkedTotal ? 'warn' : undefined}
          note={unmarkedTotal ? namesLine(unmarked.map((row) => row.cohort.name)) : t('по всем журналам')}
        />
      </div>
      <DataCard className="card--beam" title={t('Мои журналы')} count={data.rows.length}>
        <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} onRowClick={(row) => navigate(`/journals/${row.id}`)} />
      </DataCard>
    </div>
  )
}
