/**
 * Ученики группы куратора — таблица на чтение (фаза 61).
 *
 * Куратор здесь ничего не правит: он подтверждает в очереди и ставит
 * задачи. Столбцы — то, по чему он решает, кого дёргать: баллы против
 * целей, давность пробника, документы и внутренняя метка.
 *
 * Корзины считает сервер; сегменты над таблицей показывают его числа,
 * а не пересчитывают их по загруженным строкам — на второй странице
 * такой пересчёт соврал бы.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useCuratorStudents, type CuratorStudentRow } from '../../api/hooks'
import { useStudentsSections } from '../../api/sport'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import Field from '../../components/Field'
import { Avatar, Segmented } from '../../components/patterns'
import { Chip, counted, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { STATUS_TONE, useGroup } from './state'
import { formatDate } from '../../lib/format'
import '../directors/directors.css'
import './curator.css'
import './curator-layout.css'

const dateOf = (value: string | null) => (value ? formatDate(value) : null)

/** Пара «текущий → цель»: пусто читается как «нет», а не как ноль. */
function Pair({ current, target }: { current: number | null; target: number | null }) {
  return (
    <>
      <span className="num">{current ?? t('нет')}</span>
      <span className="t-note"> → {target ?? t('нет цели')}</span>
    </>
  )
}

export default function CuratorStudents() {
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [task, setTask] = useState(false)
  const [exporting, setExporting] = useState(false)

  const bucket = params.get('bucket') ?? ''
  const { data, isLoading, error } = useCuratorStudents(group, bucket, search)
  // секция и посещение секции за месяц (27.10.2026): сервер отдаёт только свои группы
  const sections = useStudentsSections(null)
  const [sectionFilter, setSectionFilter] = useState<'' | 'none' | 'skip'>('')

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const sectionOf = (row: CuratorStudentRow) => sections.data?.rows[String(row.id)]
  const loaded = data?.results ?? []
  const noSection = loaded.filter((row) => !sectionOf(row)).length
  const skipping = loaded.filter((row) => sectionOf(row)?.below).length
  const rows = loaded.filter((row) =>
    sectionFilter === 'none' ? !sectionOf(row) : sectionFilter === 'skip' ? Boolean(sectionOf(row)?.below) : true,
  )
  // у выбранных групп без поступления нет колонок IELTS, SAT и документов
  // и задачи плана; в смешанном списке у строк 8–10 эти ячейки пустые
  const admission = data?.has_admission ?? true
  const graduate = (row: CuratorStudentRow) => row.parallel === 11

  const setBucket = (code: string) => {
    const updated = new URLSearchParams(params)
    if (code) updated.set('bucket', code)
    else updated.delete('bucket')
    setParams(updated, { replace: true })
  }

  // выгрузка — по текущему фильтру; сначала предпросмотр, файл — из него
  const exportPath = () => {
    const query = new URLSearchParams()
    if (group !== 'all') query.set('group', group)
    if (bucket) query.set('bucket', bucket)
    const tail = query.toString()
    return `/curator/students/export/${tail ? `?${tail}` : ''}`
  }

  const allColumns: Column<CuratorStudentRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: '22%',
      cell: (row) => (
        <span className="personcell">
          <Avatar name={row.full_name} size={30} />
          <b>{row.full_name}</b>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    { key: 'group', title: t('Группа'), width: '10%', cell: (row) => <Chip size="sm">{row.group}</Chip>, sortBy: (row) => row.group },
    { key: 'ielts', title: 'IELTS', width: '14%', align: 'right', cell: (row) => (graduate(row) ? <Pair current={row.ielts_current} target={row.ielts_target} /> : null), sortBy: (row) => row.ielts_current },
    { key: 'sat', title: 'SAT', width: '14%', align: 'right', cell: (row) => (graduate(row) ? <Pair current={row.sat_current} target={row.sat_target} /> : null), sortBy: (row) => row.sat_current },
    {
      key: 'mock',
      title: t('Mock Test'),
      width: '12%',
      align: 'right',
      cell: (row) =>
        row.last_mock_date ? (
          <span className={row.buckets.includes('nomock') ? 'cstale' : undefined}>{dateOf(row.last_mock_date)}</span>
        ) : (
          <span className="cstale">{t('ещё не было')}</span>
        ),
      sortBy: (row) => row.days_without_mock ?? 9999,
    },
    {
      key: 'docs',
      title: t('Документы'),
      width: '12%',
      align: 'right',
      cell: (row) =>
        graduate(row) ? (
          <span className="cstudents__docs">
            <span className={`num${row.buckets.includes('docs') ? ' cstale' : ''}`}>
              {row.documents_collected} / {row.documents_total}
            </span>
            {/* полоса из тех же двух чисел */}
            <span className="cstudents__bar" aria-hidden="true">
              <i style={{ width: `${row.documents_total ? Math.round((row.documents_collected / row.documents_total) * 100) : 0}%` }} />
            </span>
          </span>
        ) : null,
      sortBy: (row) => row.documents_collected,
    },
    {
      key: 'section',
      title: t('Секция'),
      width: '13%',
      cell: (row) => {
        const info = sectionOf(row)
        if (!info) return <span className="t-note">{t('не записан')}</span>
        return (
          <>
            <b>{info.section}</b>
            <span className="t-note dir__sub">{info.slot || t('час не выбран')}</span>
          </>
        )
      },
      sortBy: (row) => sectionOf(row)?.section ?? '',
    },
    {
      key: 'section_pct',
      title: t('Посещение секции'),
      width: '15%',
      align: 'right',
      cell: (row) => {
        const info = sectionOf(row)
        if (!info) return null
        if (info.percent === null) return <span className="t-note">{t('занятий не было')}</span>
        return info.below ? (
          <Chip tone="warn" size="sm" className="num">
            {`${info.percent}%`}
          </Chip>
        ) : (
          <span className="num">{info.percent}%</span>
        )
      },
      sortBy: (row) => sectionOf(row)?.percent ?? -1,
    },
    {
      key: 'status',
      title: t('Статус'),
      width: '14%',
      cell: (row) =>
        row.status_title ? (
          <Chip tone={STATUS_TONE[row.status] ?? 'neutral'} size="sm">
            {row.status_title}
          </Chip>
        ) : (
          <span className="t-note">{t('нет')}</span>
        ),
      sortBy: (row) => row.status_title,
    },
  ]
  const columns = allColumns.filter((column) => admission || !['ielts', 'sat', 'docs'].includes(column.key))

  const groups = data?.groups ?? []
  const shownGroups = group === 'all' ? groups : groups.filter((item) => item.code === group)
  const total = shownGroups.reduce((sum, item) => sum + item.students, 0)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Ученики')}
        subtitle={
          shownGroups.length > 1
            ? t('{students} в {groups}', { students: counted(total, 'ученик|ученика|учеников'), groups: counted(shownGroups.length, 'группе|группах|группах') })
            : counted(total, 'ученик|ученика|учеников')
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
            {/* кнопка отдельно от окна (фаза 75): на телефоне она уходит
                в меню «Действия», а окно остаётся у экрана */}
            {admission && (
              <Button size="sm" onClick={() => setTask(true)}>
                {t('Задача группе')}
              </Button>
            )}
          </>
        }
      />
      {admission && <TaskDialog groups={data?.groups ?? []} defaultGroup={group} open={task} onOpenChange={setTask} />}
      <GroupSwitch groups={data?.groups ?? []} value={group} onChange={setGroup} />

      {/* корзины — фильтрами со счётчиком в одну строку; поиск — в шапке таблицы, как в макете */}
      <div className="filters cstudents__buckets">
        <Segmented
          value={sectionFilter ? `sport:${sectionFilter}` : bucket}
          onChange={(value) => {
            // «Без секции» и «Пропускают секцию» — в том же ряду, что корзины (макет CStudents)
            if (value.startsWith('sport:')) {
              setSectionFilter(value.slice(6) as 'none' | 'skip')
              setBucket('')
            } else {
              setSectionFilter('')
              setBucket(value)
            }
          }}
          label={t('Кого показать')}
          items={[
            { value: '', label: <>{t('Все')}<span className="tabs__n num">{total}</span></> },
            ...(data?.buckets ?? []).map((row) => ({
              value: row.code,
              label: (
                <>
                  {t(row.title)}
                  <span className="tabs__n num">{row.count}</span>
                </>
              ),
            })),
            { value: 'sport:none', label: <>{t('Без секции')}<span className="tabs__n num">{noSection}</span></> },
            { value: 'sport:skip', label: <>{t('Пропускают секцию')}<span className="tabs__n num">{skipping}</span></> },
          ]}
        />
      </div>

      <section className="card card-pad cstudents">
        <div className="cstudents__head">
          <Field usageFilter kind="text" name="search" label={t('Фильтр по имени')} value={search} onChange={setSearch} placeholder={t('Фильтр по имени')} className="filters__search" />
          <span className="t-note">{t('показано {count}', { count: rows.length })}</span>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/students/${row.id}`)}
          empty={<span className="t-note">{t('Никого с таким фильтром')}</span>}
          foot={<span className="t-note">{t('Статус — внутренняя метка школы. Ученик её не видит ни на одном экране.')}</span>}
        />
      </section>

      {exporting && (
        <ExportPreview
          path={exportPath()}
          fallback="students.xlsx"
          title={t('Выгрузка учеников')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}
