/**
 * Журналы учителя списком: ученики, уроки, средний ФО, СОР.
 */
import { useNavigate } from 'react-router-dom'
import { useTeacherJournals, type TeacherJournals } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { counted, DataCard, ErrorNote, Loading, ScreenHead, withNumbers } from '../../components/ui'
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
      <div>
        <ScreenHead title={t('Журналы')} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Журналов нет')} empty={t('журнал появится, когда вас поставят в расписание')} />
          </div>
        </div>
      </div>
    )

  const columns: Column<JournalRow>[] = [
    {
      key: 'title',
      title: t('Журнал'),
      width: '32%',
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
    { key: 'students', title: t('Учеников'), width: '12%', align: 'right', cell: (row) => <b className="num">{row.students}</b>, sortBy: (row) => row.students },
    {
      key: 'held',
      title: t('Уроков'),
      width: '16%',
      align: 'right',
      cell: (row) => (
        <span className="num">
          {withNumbers(t('{done} из {total}', { total: row.planned }), { done: row.held })}
          {row.unmarked > 0 && (
            <>
              <br />
              <span className="t-note">{tn(row.unmarked, '{n} не отмечен|{n} не отмечено|{n} не отмечено')}</span>
            </>
          )}
        </span>
      ),
      sortBy: (row) => row.held,
    },
    { key: 'fo', title: t('Средний ФО'), width: '14%', align: 'right', cell: (row) => (row.fo_avg === null ? <span className="t-note">{t('оценок нет')}</span> : <b className="num">{row.fo_avg}</b>), sortBy: (row) => row.fo_avg },
    {
      key: 'sor',
      title: t('СОР'),
      width: '14%',
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
      key: 'open',
      title: '',
      width: '12%',
      align: 'right',
      cell: (row) => (
        <Button variant="secondary" size="sm" onClick={() => navigate(`/journals/${row.id}`)}>
          {t('Открыть')}
        </Button>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Журналы')}
        subtitle={[data.teacher.full_name, counted(data.rows.length, 'журнал|журнала|журналов'), ...(data.quarter ? [t('{quarter} до {date}', { quarter: data.quarter.title, date: dateWords(data.quarter.ends) })] : [])].join(' · ')}
      />
      <div className="acad__cols">
        <div className="card">
          <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} onRowClick={(row) => navigate(`/journals/${row.id}`)} />
        </div>
      </div>
    </div>
  )
}
