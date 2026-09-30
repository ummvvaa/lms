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
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useCuratorStudents, type CuratorStudentRow } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import Field from '../../components/Field'
import { Segmented } from '../../components/patterns'
import { Chip, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import { formatDate } from '../../lib/format'
import './curator.css'

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

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const rows = data?.results ?? []

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

  const columns: Column<CuratorStudentRow>[] = [
    { key: 'name', title: t('Ученик'), width: '26%', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    { key: 'group', title: t('Группа'), width: '10%', cell: (row) => <Chip size="sm">{row.group}</Chip>, sortBy: (row) => row.group },
    { key: 'ielts', title: 'IELTS', width: '14%', align: 'right', cell: (row) => <Pair current={row.ielts_current} target={row.ielts_target} />, sortBy: (row) => row.ielts_current },
    { key: 'sat', title: 'SAT', width: '14%', align: 'right', cell: (row) => <Pair current={row.sat_current} target={row.sat_target} />, sortBy: (row) => row.sat_current },
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
      width: '10%',
      align: 'right',
      cell: (row) => (
        <span className={`num${row.buckets.includes('docs') ? ' cstale' : ''}`}>
          {row.documents_collected} / {row.documents_total}
        </span>
      ),
      sortBy: (row) => row.documents_collected,
    },
    {
      key: 'status',
      title: t('Статус'),
      width: '14%',
      cell: (row) => (row.status_title ? <Chip size="sm">{row.status_title}</Chip> : <span className="t-note">{t('нет')}</span>),
      sortBy: (row) => row.status_title,
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Ученики')}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
            {/* кнопка отдельно от окна (фаза 75): на телефоне она уходит
                в меню «Действия», а окно остаётся у экрана */}
            <Button size="sm" onClick={() => setTask(true)}>
              {t('Задача группе')}
            </Button>
          </>
        }
      />
      <TaskDialog groups={data?.groups ?? []} defaultGroup={group} open={task} onOpenChange={setTask} />
      <GroupSwitch groups={data?.groups ?? []} value={group} onChange={setGroup} />

      <div className="cfilters">
        <Segmented
          value={bucket}
          onChange={setBucket}
          label={t('Кого показать')}
          items={[
            { value: '', label: t('Все') },
            ...(data?.buckets ?? []).map((row) => ({
              value: row.code,
              label: (
                <>
                  {t(row.title)} <span className="gswitch__note num">{row.count}</span>
                </>
              ),
            })),
          ]}
        />
        <Field kind="text" name="search" label={t('Фильтр по имени')} value={search} onChange={setSearch} placeholder={t('Фамилия или имя')} className="cfilters__search" />
      </div>

      <div className="card">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/students/${row.id}`)}
          empty={<span className="t-note">{t('Никого с таким фильтром')}</span>}
          foot={<span className="t-note">{t('Статус — внутренняя метка школы. Ученик её не видит ни на одном экране.')}</span>}
        />
      </div>

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
