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
import { namesLine, Row, Rows, ShowAll } from '../../components/patterns'
import {
  Bar,
  Chip,
  DataCard,
  ErrorNote,
  Kpi,
  Loading,
  ScreenHead,
  ScreenTabs,
  type Tone,
} from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDate, formatDateTime } from '../../lib/format'
import { usePhone } from '../../phone'
import { GroupPick } from '../academics/shared'
import { useAuth } from '../../auth/AuthContext'
import Icon from '../../layout/icons'
import AnalysisCard from './AnalysisCard'
import CuratorCareer from './CuratorCareer'
import AssignCard from './AssignCard'
import StartAnalysisDialog from './StartAnalysisDialog'
import TestDrawer from './TestDrawer'
import StudentResultsCard from './StudentResultsCard'
import UploadCard from './UploadCard'
import './career-tests-layout.css'

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
  const list = useCareerTests()
  const patch = useCareerTestPatch()
  const [assigning, setAssigning] = useState<number | null>(null)
  // панель теста по клику на «Открыть»: состояние, порог, кому открыт, шкалы, утверждения
  const [opened, setOpened] = useState<number | null>(null)
  const detail = useCareerTest(assigning)
  if (list.isLoading) return <Loading kind="cards" />
  if (list.error) return <ErrorNote error={list.error} />
  const rows = list.data?.tests ?? []

  const toggle = (row: CareerTestRow, on: boolean) =>
    patch.mutate({ id: row.id, is_active: on }, { onError: (error) => toast.error(error.message) })
  const current = rows.find((row) => row.id === opened) ?? null
  const whoNote = (row: CareerTestRow) =>
    [formatDate(row.created_at), row.created_by?.short ?? ''].filter(Boolean).join(' · ')
  // показатели — из тех же чисел, что в карточках тестов
  const active = rows.filter((row) => row.is_active).length
  const done = rows.reduce((sum, row) => sum + row.done, 0)
  const assigned = rows.reduce((sum, row) => sum + row.assigned, 0)
  const going = rows.reduce((sum, row) => sum + row.in_progress, 0)
  const authors = [...new Set(rows.map((row) => row.created_by?.short ?? '').filter(Boolean))]

  return (
    <>
      {rows.length === 0 ? (
        <div className="lay-2">
          <DataCard
            title={t('Тесты')}
            empty={
              manage
                ? t('загрузите первый тест файлом — шаблон скачивается в окне загрузки')
                : t('учитель профориентации ещё не загрузил ни одного теста')
            }
          />
          <DataCard title={t('Как устроен файл')}>
            <p className="acad__note">
              {t(
                'Книга xlsx из пяти листов: «Тест» (название, инструкция, порог), «Ответы» (варианты и баллы), «Шкалы», «Вопросы» (номер, текст, шкала, знак) и «Интерпретация» (диапазоны баллов). Баллы считает платформа по ключу, модель разбирает только сферы выше порога.',
              )}
            </p>
          </DataCard>
        </div>
      ) : (
        <>
          <div className="lay-4">
            <Kpi label={t('Тесты')} value={rows.length} note={t('включено {n}', { n: active })} />
            <Kpi
              label={t('Сдали')}
              value={done}
              note={assigned ? t('{done} из {total}', { done, total: assigned }) : t('никому не открыт')}
            />
            <Kpi label={t('Проходят сейчас')} value={going || null} none={t('нет')} />
            <Kpi
              label={t('Загрузили')}
              value={authors.length || null}
              none={t('нет')}
              note={authors.length ? namesLine(authors) : undefined}
            />
          </div>
          {/* тесты карточками по четыре в ряд: название, кто и когда загрузил,
              сдали из скольких полосой; внизу «Кому» и «Открыть». Видны два ряда,
              остальные — «Показать все» на месте */}
          <div className="lay-4 ctl-grid">
            <ShowAll limit={8}>
              {rows.map((row) => (
                <section key={row.id} className="card card-pad ctl-test">
                  <header className="ctl-test__head">
                    <span className="ctl-test__ico" aria-hidden="true">
                      <Icon name="compass" size={20} />
                    </span>
                    {manage ? (
                      <SelectField
                        className="ctl-test__state"
                        aria-label={t('{test}: включён или выключен', { test: row.title })}
                        value={row.is_active ? 'on' : 'off'}
                        disabled={patch.isPending}
                        onChange={(event) => toggle(row, event.target.value === 'on')}
                      >
                        <option value="on">{t('включён')}</option>
                        <option value="off">{t('выключен')}</option>
                      </SelectField>
                    ) : (
                      <Chip size="sm" tone={row.is_active ? 'good' : 'neutral'}>
                        {row.is_active ? t('включён') : t('выключен')}
                      </Chip>
                    )}
                  </header>
                  <div className="ctl-test__text">
                    <b className="ctl-test__title">{row.title}</b>
                    <span className="t-note num">{whoNote(row)}</span>
                  </div>
                  <div className="ctl-test__stats">
                    <div className="ctl-test__line">
                      <span className="t-note">{t('Утверждений')}</span>
                      <b className="num">{row.items}</b>
                    </div>
                    <div className="ctl-test__line">
                      <span className="t-note">{t('Сдали')}</span>
                      {row.assigned ? (
                        <b className="num">
                          {t('{done} из {total}', { done: row.done, total: row.assigned })}
                        </b>
                      ) : (
                        <span className="t-note">{t('никому не открыт')}</span>
                      )}
                    </div>
                    <Bar percent={row.assigned ? (row.done / row.assigned) * 100 : 0} color="var(--good)" />
                  </div>
                  <div className="ctl-test__acts">
                    {manage && (
                      <Button variant="secondary" size="sm" onClick={() => setAssigning(row.id)}>
                        {t('Кому')}
                      </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => setOpened(row.id)}>
                      {t('Открыть')}
                    </Button>
                  </div>
                </section>
              ))}
            </ShowAll>
          </div>
        </>
      )}
      {assigning !== null && detail.data && (
        <AssignCard test={detail.data} onClose={() => setAssigning(null)} />
      )}
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
  if (!data || data.tests.length === 0)
    return <DataCard title={t('Результаты')} empty={t('группе ещё не открыт ни один тест')} />
  type StudentRow = CareerResults['students'][number]
  const columns: Column<StudentRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      sortBy: (row) => row.full_name,
      cell: (row) => <b>{row.full_name}</b>,
    },
    ...data.tests.map((test): Column<StudentRow> => ({
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
            <Button
              variant="link"
              size="sm"
              onClick={() => setOpened({ student: row.id, attempt: cell.attempt })}
            >
              {cell.finished_at ? formatDate(cell.finished_at) : t(meta.label)}
            </Button>
          )
        return (
          <Chip size="sm" tone={meta.tone}>
            {status === 'in_progress' && cell?.answered !== undefined
              ? t('отвечено {n}', { n: cell.answered })
              : t(meta.label)}
          </Chip>
        )
      },
    })),
  ]
  const done = data.students.filter((row) =>
    data.tests.every((test) => row.cells[String(test.id)]?.status === 'done'),
  ).length
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
      <DataCard
        title={t('Результаты')}
        note={t('Сдали все открытые тесты: {done} из {total}', { done, total: data.students.length })}
        count={data.students.length}
      >
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
                        .filter(
                          (test) =>
                            row.cells[String(test.id)]?.status === 'done' &&
                            row.cells[String(test.id)]?.attempt,
                        )
                        .map((test) => (
                          <Button
                            key={test.id}
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setOpened({ student: row.id, attempt: row.cells[String(test.id)].attempt })
                            }
                          >
                            {row.cells[String(test.id)].finished_at
                              ? formatDate(row.cells[String(test.id)].finished_at ?? '')
                              : t('Баллы')}
                          </Button>
                        ))}
                    </>
                  ) : undefined
                }
              />
            ))}
          </Rows>
        ) : (
          <DataTable
            columns={columns}
            rows={data.students}
            rowKey={(row) => row.id}
            fit
            onRowClick={(row) => setOpened({ student: row.id, attempt: null })}
          />
        )}
      </DataCard>
      {opened !== null && (
        <StudentResultsCard
          student={opened.student}
          attempt={opened.attempt}
          manage={manage}
          onClose={() => setOpened(null)}
        />
      )}
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
    {
      key: 'student',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      sortBy: (row) => row.student?.full_name ?? '',
      cell: (row) => <b>{row.student?.full_name}</b>,
    },
    {
      key: 'tests',
      title: t('Тесты'),
      width: '24%',
      cell: (row) => row.tests.map((test) => test.title).join(', '),
    },
    {
      key: 'when',
      title: t('Когда'),
      width: '16%',
      align: 'right',
      sortBy: (row) => row.created_at,
      cell: (row) => <span className="num">{formatDateTime(row.created_at)}</span>,
    },
    { key: 'state', title: t('Состояние'), width: '12%', cell: stateChip, sortBy: (row) => row.status },
    ...(data.student_sees
      ? [
          {
            key: 'shown',
            title: t('Ученику'),
            width: '12%',
            sortBy: (row) => (row.visible_to_student ? 0 : 1),
            cell: (row: CareerAnalysis) =>
              row.visible_to_student ? (
                <Chip size="sm" tone="good">
                  {t('показан')}
                </Chip>
              ) : (
                <span className="t-note">{t('нет')}</span>
              ),
          } as Column<CareerAnalysis>,
        ]
      : []),
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
          <span className="t-note">
            {t('Готовый разбор по тем же попыткам второй раз у модели не запрашивается')}
          </span>
        </div>
      )}
      {rows.length === 0 ? (
        <DataCard
          title={t('Разборы')}
          empty={
            manage
              ? t('разборов пока нет — нажмите «Разобрать», когда ученики сдадут тесты')
              : t('разборов по этой группе пока нет')
          }
        />
      ) : phone ? (
        <DataCard title={t('Разборы')} count={rows.length}>
          <Rows>
            {rows.map((row) => (
              <Row
                key={row.id}
                avatar={row.student?.full_name ?? ''}
                title={row.student?.full_name ?? ''}
                note={[row.tests.map((test) => test.title).join(', '), formatDateTime(row.created_at)].join(
                  ' · ',
                )}
                right={stateChip(row)}
                onOpen={() => setOpened(row.id)}
                openLabel={t('Открыть')}
              />
            ))}
          </Rows>
        </DataCard>
      ) : (
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} fit limit={40} />
        </div>
      )}
      {starting && (
        <StartAnalysisDialog group={group} tests={data.tests} onClose={() => setStarting(false)} />
      )}
      {current && (
        <AnalysisCard
          analysis={current}
          manage={manage}
          studentSees={data.student_sees}
          onClose={() => setOpened(null)}
        />
      )}
    </>
  )
}

// --- Экран ---------------------------------------------------------------------------

export default function CareerTests() {
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const groups = useCareerGroups()
  const [uploading, setUploading] = useState(false)
  // куратору — свой экран: вкладки по группам и результаты на чтение
  if (me?.role === 'curator') return <CuratorCareer />
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
    <div className="lay-screen ctl-screen">
      <ScreenHead
        title={t('Профтест')}
        subtitle={
          manage
            ? t('Тесты профориентации, результаты и разборы ваших групп')
            : t('Результаты и разборы тестов профориентации')
        }
        actions={
          manage ? (
            <Button size="sm" onClick={() => setUploading(true)}>
              {t('Загрузить тест')}
            </Button>
          ) : undefined
        }
      />
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
        <div className="filters">
          {list.length === 0 ? (
            <span className="t-note">{tn(0, '{n} группа|{n} группы|{n} групп')}</span>
          ) : (
            <GroupPick groups={list} value={groupCode} onChange={(code) => setParam('group', code)} />
          )}
        </div>
      )}
      {tab === 'tests' && <TestsTab manage={manage} />}
      {tab === 'results' && <ResultsTab group={groupId} manage={manage} />}
      {tab === 'analyses' && <AnalysesTab group={groupId} manage={manage} />}
      {uploading && <UploadCard onClose={() => setUploading(false)} />}
    </div>
  )
}
