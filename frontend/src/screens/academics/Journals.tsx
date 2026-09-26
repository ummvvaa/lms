/**
 * Журналы учителя списком: ученики, уроки, средний ФО, СОР.
 */
import { useNavigate } from 'react-router-dom'
import { useTeacherJournals, type TeacherJournals } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateWords, NoteCard } from './shared'

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
          <div className="acad__stack">
            <NoteCard title={t('Что такое журнал')}>
              {t('Один журнал — один предмет у одного состава: группы, подгруппы или потока. Слева ученики, по верху уроки, в каждом уроке посещаемость и оценка рядом.')}
            </NoteCard>
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
          <b>{row.held}</b> {t('из')} {row.planned}
          {row.unmarked > 0 && (
            <>
              <br />
              <span className="t-note">{`${row.unmarked} ${t('не отмечено')}`}</span>
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
            <b>{row.sor_done}</b> {t('из')} {row.sor_all}
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
        subtitle={`${data.teacher.full_name} · ${counted(data.rows.length, ['журнал', 'журнала', 'журналов'])}${data.quarter ? ` · ${data.quarter.title} ${t('до')} ${dateWords(data.quarter.ends)}` : ''}`}
      />
      <div className="acad__cols">
        <div className="card">
          <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} onRowClick={(row) => navigate(`/journals/${row.id}`)} />
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Как устроен журнал')}>
            {t('В каждом уроке две клетки: слева посещаемость, справа оценка. Нажмите клетку или выделите её и печатайте: цифра — оценка,')}{' '}
            <span className="acad__kbd">н</span> {t('— не был,')} <span className="acad__kbd">о</span> {t('— опоздал, стрелки — соседняя клетка.')}
          </NoteCard>
          <NoteCard title={t('Итог четверти')}>
            {t('Считается сам:')} {t('ФО')} {data.scale.weight_fo} %, {t('СОР')} {data.scale.weight_sor} %, {t('СОЧ')} {data.scale.weight_soch} %.{' '}
            {data.quarter ? `${t('В последнюю неделю, до')} ${dateWords(data.quarter.ends)}, ${t('выставьте итог кнопкой в журнале.')}` : ''}{' '}
            {t('Оценку старше')} {data.scale.edit_days} {t('дней правит Кымбат.')}
          </NoteCard>
        </div>
      </div>
    </div>
  )
}
