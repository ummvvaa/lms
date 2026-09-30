/**
 * Экран «Документы» куратора (фаза 62).
 *
 * Сверху пять чисел «собрано / всего» по типам, сегменты фильтра, таблица
 * ученик × тип. Нажатие на клетку: есть файл — предпросмотр с решением,
 * файла нет — задача ученику «Загрузить: тип». «Напомнить всем» — по задаче
 * каждому со списком именно его недостающих, по выбранной группе (D64).
 * Всё считает сервер (`students.documents`): числа здесь, столбец в таблице
 * учеников, число на главной и корзина не расходятся.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAssignTask, useCuratorDocuments, useRemindDocuments, type DocumentCell } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import Modal from '../../components/Modal'
import { Segmented, StatRow } from '../../components/patterns'
import { ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { daysFromToday } from '../../lib/dates'
import DocumentPreview, { STATE_TITLE, type PreviewTarget } from './DocumentPreview'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import './curator.css'

const FILTERS: { code: string; label: string }[] = [
  { code: '', label: tk('Все') },
  { code: 'missing', label: tk('Не собраны') },
  { code: 'pending', label: tk('Ждут проверки') },
  { code: 'expiring', label: tk('Истекает срок') },
]

/** Знаки ячеек — буквы и знаки препинания, не эмодзи: истекающий отличается пунктирной рамкой */
// нет документа — пустая клетка, не прочерк (правило вида)
const MARK: Record<string, string> = { confirmed: '✓', pending: '…', rejected: '!', expiring: '!', none: '' }

/** Документ-ссылка (фаза 65): файла нет, есть адрес вне системы. */
const LINK_MARK = '↗'

/** Срок задачи по умолчанию — неделя, как у напоминания всем. */
function inAWeek(): string {
  return daysFromToday(7)
}

type DocumentsMatrixRow = {
  id: number
  full_name: string
  group: string
  collected: number
  total: number
  cells: DocumentCell[]
}

export default function CuratorDocuments() {
  const navigate = useNavigate()
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const filter = params.get('f') ?? ''
  const { data, isLoading, error } = useCuratorDocuments(group, filter)
  const remind = useRemindDocuments()
  const assign = useAssignTask()
  const [preview, setPreview] = useState<PreviewTarget | null>(null)
  const [remindAll, setRemindAll] = useState(false)
  const [exporting, setExporting] = useState(false)

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const setFilter = (code: string) => {
    const updated = new URLSearchParams(params)
    if (code) updated.set('f', code)
    else updated.delete('f')
    setParams(updated, { replace: true })
  }

  const openCell = (row: DocumentsMatrixRow, cell: DocumentCell, title: string) => {
    if (cell.document) {
      setPreview({
        id: cell.document,
        title,
        studentName: row.full_name,
        fileName: cell.file_name,
        contentType: cell.content_type,
        isLink: cell.is_link ?? false,
        externalUrl: cell.external_url ?? '',
        state: cell.state,
        expiresAt: cell.expires_at,
        rejectReason: cell.reject_reason,
        suggestion: cell.suggestion,
      })
      return
    }
    assign.mutate(
      { student: row.id, title: t('Загрузить: {document}', { document: t(title) }), due_date: inAWeek() },
      {
        onSuccess: () => toast.success(t('Задача ученику: {document}', { document: t(title) })),
        onError: (e) => toast.error(e.message),
      },
    )
  }

  // выгрузка матрицы — по текущему фильтру; сначала предпросмотр, файл — из него
  const exportPath = () => {
    const query = new URLSearchParams()
    if (group !== 'all') query.set('group', group)
    if (filter) query.set('f', filter)
    const tail = query.toString()
    return `/curator/documents/export/${tail ? `?${tail}` : ''}`
  }

  // число в окне и адресат напоминания — одна и та же группа (D64)
  const scopeWords = group === 'all' ? t('по всем вашим группам') : t('по группе {group}', { group })

  const columns: Column<DocumentsMatrixRow>[] = [
    { key: 'name', title: t('Ученик'), width: '26%', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    { key: 'group', title: t('Группа'), width: '10%', cell: (row) => row.group, sortBy: (row) => row.group },
    ...data.types.map((type, index) => ({
      key: type.code,
      title: t(type.title),
      width: `${Math.floor(54 / Math.max(1, data.types.length))}%`,
      cell: (row: DocumentsMatrixRow) => {
        const cell = row.cells[index]
        if (!cell) return null
        return (
          <Button
            variant="ghost"
            size="icon-sm"
            className={`cdocs__cell cdocs__cell--${cell.state}`}
            title={`${t(type.title)}: ${[t(STATE_TITLE[cell.state]), cell.is_link ? t('внешняя ссылка') : ''].filter(Boolean).join(' · ')}`}
            aria-label={`${row.full_name}, ${t(type.title)}: ${t(STATE_TITLE[cell.state])}`}
            onClick={(event) => {
              event.stopPropagation()
              openCell(row, cell, type.title)
            }}
          >
            {cell.is_link ? LINK_MARK : MARK[cell.state]}
          </Button>
        )
      },
    })),
    { key: 'sum', title: t('Собрано'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.collected} / {row.total}</span>, sortBy: (row) => row.collected },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Документы')}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
            <Button size="sm" onClick={() => setRemindAll(true)} disabled={data.missing_students === 0}>
              {t('Напомнить всем, у кого не хватает')}
            </Button>
          </>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <StatRow>
        {data.counts.map((count) => (
          <Kpi
            key={count.code}
            tone={count.collected === count.total ? 'good' : 'accent'}
            label={t(count.title)}
            value={`${count.collected} / ${count.total}`}
            onClick={() => setFilter('missing')}
          />
        ))}
      </StatRow>

      <div className="cfilters">
        <Segmented
          value={filter}
          onChange={setFilter}
          label={t('Какие документы')}
          items={FILTERS.map((item) => ({
            value: item.code,
            label: item.code ? (
              <>
                {t(item.label)} <span className="gswitch__note num">{data.filters[item.code as keyof typeof data.filters]}</span>
              </>
            ) : (
              t(item.label)
            ),
          }))}
        />
        <span className="t-note cdocs__legend">
          {Object.entries(MARK).map(([state, mark]) => (
            <span key={state} className="cdocs__key">
              <span className={`cdocs__cell cdocs__cell--${state} cdocs__cell--key`}>{mark}</span> {t(STATE_TITLE[state])}
            </span>
          ))}
          <span className="cdocs__key">
            <span className="cdocs__cell cdocs__cell--confirmed cdocs__cell--key">{LINK_MARK}</span> {t('внешняя ссылка')}
          </span>
        </span>
      </div>

      <div className="card">
        <DataTable
          columns={columns}
          rows={data.results}
          rowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/students/${row.id}?tab=documents`)}
          empty={<span className="t-note">{t('По этому фильтру никого')}</span>}
        />
      </div>

      {preview && <DocumentPreview target={preview} onClose={() => setPreview(null)} />}

      {remindAll && (
        <Modal title={t('Напомнить о документах')} note={scopeWords} onClose={() => setRemindAll(false)}>
          <p className="acad__note">
            {t('Учеников без полного набора:')} <b className="num">{data.missing_students}</b>. {t('Каждому уйдёт задача со списком именно его недостающих, срок — 7 дней.')}
          </p>
          <p className="t-note">{t('Задача видна ученику в календаре и на его доске.')}</p>
          <div className="acad__actions">
            <Button
              disabled={remind.isPending}
              onClick={() =>
                remind.mutate(group === 'all' ? {} : { group }, {
                  onSuccess: (result) => {
                    toast.success(`${t('Задача отправлена ученикам:')} ${result.created}`)
                    setRemindAll(false)
                  },
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              {tn(data.missing_students, 'Отправить {n} ученику|Отправить {n} ученикам|Отправить {n} ученикам')}
            </Button>
            <Button variant="outline" onClick={() => setRemindAll(false)}>
              {t('Отмена')}
            </Button>
          </div>
        </Modal>
      )}

      {exporting && (
        <ExportPreview
          path={exportPath()}
          fallback="documents.xlsx"
          title={t('Выгрузка документов')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}
