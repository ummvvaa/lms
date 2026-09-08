/**
 * Ученики группы куратора — таблица на чтение (фаза 61).
 *
 * Куратор здесь ничего не правит: он подтверждает в очереди и ставит
 * задачи. Столбцы — то, по чему он решает, кого дёргать: баллы против
 * целей, давность пробника и внутренняя метка.
 *
 * Корзины считает сервер; чипы над таблицей показывают его числа,
 * а не пересчитывают их по загруженным строкам — на второй странице
 * такой пересчёт соврал бы.
 *
 * Столбец «Документы» появится в фазе 62.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { useCuratorStudents, type CuratorStudentRow } from '../../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import './curator.css'

type SortKey = 'full_name' | 'group' | 'ielts' | 'sat' | 'mock' | 'docs' | 'status'

const dateOf = (value: string | null) => (value ? new Date(value).toLocaleDateString('ru') : null)

/** Пара «текущий → цель»: пусто читается как «нет», а не как ноль. */
function Pair({ current, target }: { current: number | null; target: number | null }) {
  return (
    <>
      <span className="num">{current ?? '—'}</span> <span className="muted">→ {target ?? t('нет цели')}</span>
    </>
  )
}

function sortValue(row: CuratorStudentRow, key: SortKey): string | number {
  switch (key) {
    case 'group':
      return row.group
    case 'ielts':
      return row.ielts_current ?? -1
    case 'sat':
      return row.sat_current ?? -1
    case 'mock':
      return row.days_without_mock ?? 9999
    case 'docs':
      return row.documents_collected
    case 'status':
      return row.status_title
    default:
      return row.full_name
  }
}

export default function CuratorStudents() {
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'full_name', dir: 1 })

  const bucket = params.get('bucket') ?? ''
  const { data, isLoading, error } = useCuratorStudents(group, bucket, search)

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const rows = [...(data?.results ?? [])].sort((a, b) => {
    const x = sortValue(a, sort.key)
    const y = sortValue(b, sort.key)
    const cmp =
      typeof x === 'string' && typeof y === 'string' ? x.localeCompare(y, 'ru') : Number(x) - Number(y)
    return cmp * sort.dir
  })

  const setBucket = (code: string) => {
    const updated = new URLSearchParams(params)
    if (code) updated.set('bucket', code)
    else updated.delete('bucket')
    setParams(updated, { replace: true })
  }

  const head = (key: SortKey, label: string, right = false) => (
    <th className={right ? 'r' : undefined}>
      <button
        type="button"
        className="cthead"
        onClick={() => setSort((prev) => ({ key, dir: prev.key === key && prev.dir === 1 ? -1 : 1 }))}
      >
        {label}
        {sort.key === key && <span aria-hidden> {sort.dir === 1 ? '↑' : '↓'}</span>}
      </button>
    </th>
  )

  const download = () => {
    const query = new URLSearchParams()
    if (group !== 'all') query.set('group', group)
    if (bucket) query.set('bucket', bucket)
    const tail = query.toString()
    void downloadFile(`/curator/students/export/${tail ? `?${tail}` : ''}`, 'students.xlsx').catch(() =>
      toast.error(t('Не удалось собрать файл')),
    )
  }

  return (
    <div>
      <ScreenHead
        title={t('Ученики')}
        subtitle={t('Только чтение: данные вносит ученик, вы подтверждаете их в очереди')}
        actions={
          <>
            <Button variant="outline" onClick={download}>
              {t('Выгрузить')}
            </Button>
            <TaskDialog groups={data?.groups ?? []} defaultGroup={group} label={t('Задача группе')} />
          </>
        }
      />
      <GroupSwitch groups={data?.groups ?? []} value={group} onChange={setGroup} />

      <div className="cfilters">
        <button
          type="button"
          className={`cchip${bucket === '' ? ' cchip--on' : ''}`}
          onClick={() => setBucket('')}
        >
          {t('Все')}
        </button>
        {(data?.buckets ?? []).map((row) => (
          <button
            key={row.code}
            type="button"
            title={t(row.hint)}
            className={`cchip${bucket === row.code ? ' cchip--on' : ''}`}
            onClick={() => setBucket(row.code)}
          >
            {t(row.title)} <span className="cchip__note">{row.count}</span>
          </button>
        ))}
        <span className="cfilters__spacer" />
        <Input
          className="cfilters__search"
          placeholder={t('Фильтр по имени')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t('Фильтр по имени')}
        />
      </div>

      <div className="card card-pad">
        <div className="tblwrap">
          <table className="tbl">
            {/* ширины заданы явно: у таблицы `table-layout: fixed`, и без
                колонок статус «Работает самостоятельно» обрезается по краю */}
            <colgroup>
              <col style={{ width: '26%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '14%' }} />
            </colgroup>
            <thead>
              <tr>
                {head('full_name', t('Ученик'))}
                {head('group', t('Группа'))}
                {head('ielts', 'IELTS', true)}
                {head('sat', 'SAT', true)}
                {head('mock', t('Пробник'), true)}
                {head('docs', t('Документы'), true)}
                {head('status', t('Статус'))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="crow" onClick={() => navigate(`/students/${row.id}`)}>
                  <td data-head="">
                    <b>{row.full_name}</b>
                  </td>
                  <td data-label={t('Группа')}>
                    <Badge variant="mute">{row.group}</Badge>
                  </td>
                  <td data-label="IELTS" className="r">
                    <Pair current={row.ielts_current} target={row.ielts_target} />
                  </td>
                  <td data-label="SAT" className="r">
                    <Pair current={row.sat_current} target={row.sat_target} />
                  </td>
                  <td data-label={t('Пробник')} className="r">
                    {row.last_mock_date ? (
                      <span className={row.buckets.includes('nomock') ? 'cstale' : undefined}>
                        {dateOf(row.last_mock_date)}
                      </span>
                    ) : (
                      <span className="cstale">{t('не было')}</span>
                    )}
                  </td>
                  <td data-label={t('Документы')} className="r num">
                    <span className={row.buckets.includes('docs') ? 'cstale' : undefined}>
                      {row.documents_collected} / {row.documents_total}
                    </span>
                  </td>
                  <td data-label={t('Статус')}>
                    {row.status_title ? (
                      <Badge variant="mute">{row.status_title}</Badge>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="muted">{t('Никого с таким фильтром')}</p>}
      </div>

      <p className="muted cnote__small">
        {t('Статус — внутренняя метка школы. Ученик её не видит ни на одном экране.')}
      </p>
    </div>
  )
}
