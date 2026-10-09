/**
 * Профтест у учителя профориентации и администратора: тесты файлом, результаты
 * по группе, разборы моделью. Читатели результатов (Асем, куратор) видят вкладки
 * без кнопок записи. Вкладка и группа живут в адресе (`?tab=&group=`).
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  useCareerAnalyses,
  useCareerGroups,
  useCareerResults,
  useCareerTest,
  useCareerTestPatch,
  useCareerTests,
  type CareerAnalysis,
  type CareerResults,
  type CareerTestRow,
  type CellStatus,
} from '../../api/career'
import DataTable, { type Column } from '../../components/DataTable'
import { SelectField } from '../../components/SelectField'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDate, formatDateTime } from '../../lib/format'
import { usePhone } from '../../phone'
import { GroupPick } from '../academics/shared'
import AnalysisCard from './AnalysisCard'
import AssignCard from './AssignCard'
import StartAnalysisDialog from './StartAnalysisDialog'
import TestDrawer from './TestDrawer'
import StudentResultsCard from './StudentResultsCard'
import UploadCard from './UploadCard'

type Tab = 'tests' | 'results' | 'analyses'
const TABS: Tab[] = ['tests', 'results', 'analyses']

const CELL: Record<CellStatus, { tone: Tone; label: string }> = {
  none: { tone: 'neutral', label: tk('не открыт') },
  assigned: { tone: 'neutral', label: tk('не начат') },
  in_progress: { tone: 'warn', label: tk('идёт') },
  done: { tone: 'good', label: tk('сдан') },
}

// --- Тесты ------------------------------------------------------------------------

function TestsTab({ manage }: { manage: boolean }) {
  const phone = usePhone()
  const list = useCareerTests()
  const patch = useCareerTestPatch()
  const [uploading, setUploading] = useState(false)
  const [assigning, setAssigning] = useState<number | null>(null)
  // панель теста по клику на строку: состояние, порог, кому открыт, шкалы, утверждения
  const [opened, setOpened] = useState<number | null>(null)
  const detail = useCareerTest(assigning)
  if (list.isLoading) return <Loading kind="table" />
  if (list.error) return <ErrorNote error={list.error} />
  const rows = list.data?.tests ?? []

  const toggle = (row: CareerTestRow, on: boolean) => patch.mutate({ id: row.id, is_active: on }, { onError: (error) => toast.error(error.message) })
  const current = rows.find((row) => row.id === opened) ?? null
  const whoNote = (row: CareerTestRow) => [formatDate(row.created_at), row.created_by?.short ?? ''].filter(Boolean).join(' · ')
  const doneNote = (row: CareerTestRow) => t('{done} из {total}', { done: row.done, total: row.assigned })

  const columns: Column<CareerTestRow>[] = [
    {
      key: 'title',
      title: t('Тест'),
      width: 'auto',
      phone: 'head',
      sortBy: (row) => row.title,
      cell: (row) => (
        <>
          <b>{row.title}</b>
          <span className="t-note"> · {whoNote(row)}</span>
        </>
      ),
    },
    { key: 'items', title: t('Утверждений'), width: '12%', align: 'right', sortBy: (row) => row.items, cell: (row) => <span className="num">{row.items}</span> },
    {
      key: 'done',
      title: t('Сдали'),
      width: '18%',
      sortBy: (row) => (row.assigned ? row.done / row.assigned : 0),
      cell: (row) =>
        row.assigned ? (
          <span className="hwlist__done">
            <Bar percent={(row.done / row.assigned) * 100} color="var(--good)" />
            <span className="num">{doneNote(row)}</span>
          </span>
        ) : (
          <span className="t-note">{t('никому не открыт')}</span>
        ),
    },
    {
      key: 'state',
      title: t('Состояние'),
      width: '16%',
      sortBy: (row) => (row.is_active ? 0 : 1),
      cell: (row) =>
        manage ? (
          <SelectField aria-label={t('{test}: включён или выключен', { test: row.title })} value={row.is_active ? 'on' : 'off'} disabled={patch.isPending} onChange={(event) => toggle(row, event.target.value === 'on')}>
            <option value="on">{t('включён')}</option>
            <option value="off">{t('выключен')}</option>
          </SelectField>
        ) : (
          <Chip size="sm" tone={row.is_active ? 'good' : 'neutral'}>
            {row.is_active ? t('включён') : t('выключен')}
          </Chip>
        ),
    },
    {
      key: 'acts',
      title: '',
      width: '200px',
      actions: true,
      cell: (row) => (
        <>
          {manage && (
            <Button variant="secondary" size="sm" onClick={() => setAssigning(row.id)}>
              {t('Кому')}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setOpened(row.id)}>
            {t('Открыть')}
          </Button>
        </>
      ),
    },
  ]

  return (
    <>
      {rows.length === 0 ? (
        <div className="acad__cols acad__cols--even">
          <DataCard title={t('Тесты')} empty={manage ? t('загрузите первый тест файлом — шаблон скачивается в окне загрузки') : t('учитель профориентации ещё не загрузил ни одного теста')} />
          <DataCard title={t('Как устроен файл')}>
            <p className="acad__note">{t('Книга xlsx из пяти листов: «Тест» (название, инструкция, порог), «Ответы» (варианты и баллы), «Шкалы», «Вопросы» (номер, текст, шкала, знак) и «Интерпретация» (диапазоны баллов). Баллы считает платформа по ключу, модель разбирает только сферы выше порога.')}</p>
          </DataCard>
        </div>
      ) : phone ? (
        <DataCard title={t('Тесты')} count={rows.length}>
          <Rows>
            {rows.map((row) => (
              <Row
                key={row.id}
                icon="compass"
                tone={row.is_active ? 'good' : 'neutral'}
                title={row.title}
                note={[row.is_active ? t('включён') : t('выключен'), row.assigned ? t('сдали {done} из {total}', { done: row.done, total: row.assigned }) : t('никому не открыт')].join(' · ')}
                onOpen={() => setOpened(row.id)}
                openLabel={t('Открыть')}
                acts={
                  manage ? (
                    <Button variant="secondary" size="sm" onClick={() => setAssigning(row.id)}>
                      {t('Кому')}
                    </Button>
                  ) : undefined
                }
              />
            ))}
          </Rows>
        </DataCard>
      ) : (
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} fit onRowClick={(row) => setOpened(row.id)} />
        </div>
      )}
      {manage && (
        <div className="toolbar">
          <Button size="sm" onClick={() => setUploading(true)}>
            {t('Загрузить тест')}
          </Button>
        </div>
      )}
      {uploading && <UploadCard onClose={() => setUploading(false)} />}
      {assigning !== null && detail.data && <AssignCard test={detail.data} onClose={() => setAssigning(null)} />}
      {current && <TestDrawer row={current} manage={manage} onClose={() => setOpened(null)} />}
    </>
  )
}

// --- Результаты ---------------------------------------------------------------------

function ResultsTab({ group, manage }: { group: number | null; manage: boolean }) {
  const phone = usePhone()
  const results = useCareerResults(group)
  // окно результатов ученика: по клику на строку или на дату сдачи
  const [opened, setOpened] = useState<{ student: number; attempt: number | null } | null>(null)
  if (group === null) return <DataCard title={t('Результаты')} empty={t('выберите группу')} />
  if (results.isLoading) return <Loading kind="table" />
  if (results.error) return <ErrorNote error={results.error} />
  const data = results.data
  if (!data || data.tests.length === 0) return <DataCard title={t('Результаты')} empty={t('группе ещё не открыт ни один тест')} />
  type StudentRow = CareerResults['students'][number]
  const columns: Column<StudentRow>[] = [
    { key: 'name', title: t('Ученик'), width: 'auto', phone: 'head', sortBy: (row) => row.full_name, cell: (row) => <b>{row.full_name}</b> },
    ...data.tests.map(
      (test): Column<StudentRow> => ({
        key: `test-${test.id}`,
        title: test.title,
        width: `${Math.max(14, Math.floor(60 / data.tests.length))}%`,
        sortBy: (row) => row.cells[String(test.id)]?.status ?? 'none',
        cell: (row) => {
          const cell = row.cells[String(test.id)]
          const status = cell?.status ?? 'none'
          const meta = CELL[status]
          if (status === 'done' && cell.attempt)
            return (
              <Button variant="link" size="sm" onClick={() => setOpened({ student: row.id, attempt: cell.attempt })}>
                {cell.finished_at ? formatDate(cell.finished_at) : t(meta.label)}
              </Button>
            )
          return (
            <Chip size="sm" tone={meta.tone}>
              {status === 'in_progress' && cell?.answered !== undefined ? t('отвечено {n}', { n: cell.answered }) : t(meta.label)}
            </Chip>
          )
        },
      }),
    ),
  ]
  const done = data.students.filter((row) => data.tests.every((test) => row.cells[String(test.id)]?.status === 'done')).length
  // телефон: строка на ученика, состояние по каждому тесту — словами, сданный — кнопкой с датой
  const cellWords = (row: StudentRow) =>
    data.tests
      .map((test) => {
        const cell = row.cells[String(test.id)]
        const status = cell?.status ?? 'none'
        return `${test.title}: ${status === 'in_progress' && cell?.answered !== undefined ? t('отвечено {n}', { n: cell.answered }) : t(CELL[status].label)}`
      })
      .join(' · ')
  return (
    <>
      <DataCard title={t('Результаты')} note={t('Сдали все открытые тесты: {done} из {total}', { done, total: data.students.length })} count={data.students.length}>
        {phone ? (
          <Rows>
            {data.students.map((row) => (
              <Row
                key={row.id}
                avatar={row.full_name}
                title={row.full_name}
                note={cellWords(row)}
                onOpen={() => setOpened({ student: row.id, attempt: null })}
                openLabel={t('Открыть')}
                acts={
                  data.tests.some((test) => row.cells[String(test.id)]?.status === 'done') ? (
                    <>
                      {data.tests
                        .filter((test) => row.cells[String(test.id)]?.status === 'done' && row.cells[String(test.id)]?.attempt)
                        .map((test) => (
                          <Button key={test.id} variant="outline" size="sm" onClick={() => setOpened({ student: row.id, attempt: row.cells[String(test.id)].attempt })}>
                            {row.cells[String(test.id)].finished_at ? formatDate(row.cells[String(test.id)].finished_at ?? '') : t('Баллы')}
                          </Button>
                        ))}
                    </>
                  ) : undefined
                }
              />
            ))}
          </Rows>
        ) : (
          <DataTable columns={columns} rows={data.students} rowKey={(row) => row.id} fit onRowClick={(row) => setOpened({ student: row.id, attempt: null })} />
        )}
      </DataCard>
      {opened !== null && <StudentResultsCard student={opened.student} attempt={opened.attempt} manage={manage} onClose={() => setOpened(null)} />}
    </>
  )
}

// --- Разборы ----------------------------------------------------------------------

function AnalysesTab({ group, manage }: { group: number | null; manage: boolean }) {
  const phone = usePhone()
  const query = useCareerAnalyses(group)
  const [starting, setStarting] = useState(false)
  const [opened, setOpened] = useState<number | null>(null)
  if (group === null) return <DataCard title={t('Разборы')} empty={t('выберите группу')} />
  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />
  const data = query.data
  if (!data) return null
  const rows = data.analyses
  const current = rows.find((row) => row.id === opened) ?? null
  const stateChip = (row: CareerAnalysis) => (
    <Chip size="sm" tone={row.status === 'done' ? 'good' : row.status === 'failed' ? 'bad' : 'warn'}>
      {row.status_title}
    </Chip>
  )
  const columns: Column<CareerAnalysis>[] = [
    { key: 'student', title: t('Ученик'), width: 'auto', phone: 'head', sortBy: (row) => row.student?.full_name ?? '', cell: (row) => <b>{row.student?.full_name}</b> },
    { key: 'tests', title: t('Тесты'), width: '24%', cell: (row) => row.tests.map((test) => test.title).join(', ') },
    { key: 'when', title: t('Когда'), width: '16%', align: 'right', sortBy: (row) => row.created_at, cell: (row) => <span className="num">{formatDateTime(row.created_at)}</span> },
    { key: 'state', title: t('Состояние'), width: '12%', cell: stateChip, sortBy: (row) => row.status },
    ...(data.student_sees ? [{
      key: 'shown',
      title: t('Ученику'),
      width: '12%',
      sortBy: (row) => (row.visible_to_student ? 0 : 1),
      cell: (row: CareerAnalysis) => (row.visible_to_student ? <Chip size="sm" tone="good">{t('показан')}</Chip> : <span className="t-note">{t('нет')}</span>),
    } as Column<CareerAnalysis>] : []),
    {
      key: 'open',
      title: '',
      width: '110px',
      actions: true,
      cell: (row) => (
        <Button variant="secondary" size="sm" onClick={() => setOpened(row.id)}>
          {t('Открыть')}
        </Button>
      ),
    },
  ]
  return (
    <>
      {manage && (
        <div className="toolbar">
          <Button size="sm" onClick={() => setStarting(true)}>
            {t('Разобрать')}
          </Button>
          <span className="t-note">{t('Готовый разбор по тем же попыткам второй раз у модели не запрашивается')}</span>
        </div>
      )}
      {rows.length === 0 ? (
        <DataCard title={t('Разборы')} empty={manage ? t('разборов пока нет — нажмите «Разобрать», когда ученики сдадут тесты') : t('разборов по этой группе пока нет')} />
      ) : phone ? (
        <DataCard title={t('Разборы')} count={rows.length}>
          <Rows>
            {rows.map((row) => (
              <Row key={row.id} avatar={row.student?.full_name ?? ''} title={row.student?.full_name ?? ''} note={[row.tests.map((test) => test.title).join(', '), formatDateTime(row.created_at)].join(' · ')} right={stateChip(row)} onOpen={() => setOpened(row.id)} openLabel={t('Открыть')} />
            ))}
          </Rows>
        </DataCard>
      ) : (
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} fit limit={40} />
        </div>
      )}
      {starting && <StartAnalysisDialog group={group} tests={data.tests} onClose={() => setStarting(false)} />}
      {current && <AnalysisCard analysis={current} manage={manage} studentSees={data.student_sees} onClose={() => setOpened(null)} />}
    </>
  )
}

// --- Экран ---------------------------------------------------------------------------

export default function CareerTests() {
  const [params, setParams] = useSearchParams()
  const groups = useCareerGroups()
  const asked = params.get('tab') as Tab | null
  const tab: Tab = asked && TABS.includes(asked) ? asked : 'tests'
  const list = groups.data?.groups ?? []
  const manage = groups.data?.manage ?? false
  const wanted = params.get('group') ?? ''
  const groupCode = list.some((g) => g.code === wanted) ? wanted : (list[0]?.code ?? '')
  const groupId = list.find((g) => g.code === groupCode)?.id ?? null
  const setParam = (key: string, value: string) => {
    const copy = new URLSearchParams(params)
    copy.set(key, value)
    setParams(copy, { replace: true })
  }
  if (groups.isLoading) return <Loading kind="cards" />
  if (groups.error) return <ErrorNote error={groups.error} />

  return (
    <div>
      <ScreenHead title={t('Профтест')} subtitle={manage ? t('Тесты профориентации, результаты и разборы ваших групп') : t('Результаты и разборы тестов профориентации')} />
      <ScreenTabs
        value={tab}
        onChange={(next) => setParam('tab', next)}
        items={[
          { value: 'tests', label: t('Тесты') },
          { value: 'results', label: t('Результаты') },
          { value: 'analyses', label: t('Разборы') },
        ]}
      />
      {tab !== 'tests' && (
        <div className="acad__toolbar">
          {list.length === 0 ? <span className="t-note">{tn(0, '{n} группа|{n} группы|{n} групп')}</span> : <GroupPick groups={list} value={groupCode} onChange={(code) => setParam('group', code)} />}
        </div>
      )}
      {tab === 'tests' && <TestsTab manage={manage} />}
      {tab === 'results' && <ResultsTab group={groupId} manage={manage} />}
      {tab === 'analyses' && <AnalysesTab group={groupId} manage={manage} />}
    </div>
  )
}
