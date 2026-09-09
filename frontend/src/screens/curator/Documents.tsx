/**
 * Экран «Документы» куратора (фаза 62).
 *
 * Сверху пять чисел «собрано / всего» по типам, фильтры, матрица ученик × тип.
 * Клик по ячейке: есть файл — предпросмотр с решением, файла нет — задача
 * ученику «Загрузить: тип». «Напомнить всем» — по задаче каждому со списком
 * именно его недостающих. Всё считает сервер (`students.documents`): числа
 * здесь, столбец в таблице учеников, число на главной и корзина не расходятся.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import LetterDialog, { type LetterTarget } from '../../components/LetterDialog'
import { useSearchParams } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { useAssignTask, useCuratorDocuments, useRemindDocuments, type DocumentCell } from '../../api/hooks'
import Modal from '../../components/Modal'
import { StatCard, StatRow } from '../../components/patterns'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import DocumentPreview, { STATE_TITLE, type PreviewTarget } from './DocumentPreview'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import './curator.css'

const FILTERS: { code: string; label: string }[] = [
  { code: '', label: 'Все' },
  { code: 'missing', label: 'Не собраны' },
  { code: 'pending', label: 'Ждут проверки' },
  { code: 'expiring', label: 'Истекает срок' },
]

/** Знаки ячеек — буквы и знаки препинания, не эмодзи: истекающий отличается пунктирной рамкой */
const MARK: Record<string, string> = { confirmed: '✓', pending: '…', rejected: '!', expiring: '!', none: '–' }

/** Документ-ссылка (фаза 65): файла нет, есть адрес вне системы. */
const LINK_MARK = '↗'

/** Срок задачи по умолчанию — неделя, как у напоминания всем. */
function inAWeek(): string {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  return date.toISOString().slice(0, 10)
}

export default function CuratorDocuments() {
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const filter = params.get('f') ?? ''
  const { data, isLoading, error } = useCuratorDocuments(group, filter)
  const remind = useRemindDocuments()
  const assign = useAssignTask()
  const [preview, setPreview] = useState<PreviewTarget | null>(null)
  const [letter, setLetter] = useState<LetterTarget | null>(null)
  const [remindAll, setRemindAll] = useState(false)

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
      { student: row.id, title: `${t('Загрузить:')} ${t(title)}`, due_date: inAWeek() },
      {
        onSuccess: () => toast.success(`${t('Задача ученику:')} ${t(title)}`),
        onError: (e) => toast.error(e.message),
      },
    )
  }

  const download = () => {
    const query = new URLSearchParams()
    if (group !== 'all') query.set('group', group)
    if (filter) query.set('f', filter)
    const tail = query.toString()
    void downloadFile(`/curator/documents/export/${tail ? `?${tail}` : ''}`, 'documents.xlsx').catch(() =>
      toast.error(t('Не удалось собрать файл')),
    )
  }

  return (
    <div>
      <ScreenHead
        title={t('Документы')}
        subtitle={t('Ученик загружает файлы сам. Вы проверяете, что документ тот и читаемый.')}
        actions={
          <>
            <Button variant="outline" onClick={download}>
              {t('Выгрузить')}
            </Button>
            {/* письмо всем, у кого не хватает (фаза 66): задача идёт ученику
                в систему, письмо — родителям в почту. Адреса собирает сервер,
                у кого почты нет — показаны отдельным списком */}
            <Button
              variant="outline"
              disabled={data.missing_students === 0}
              onClick={() =>
                setLetter({
                  students: data.results.filter((row) => row.collected < row.total).map((row) => row.id),
                  kind: 'document',
                  ask: t('недостающие документы'),
                  title: t('Письмо о документах'),
                })
              }
            >
              {t('Письмо')}
            </Button>
            <Button onClick={() => setRemindAll(true)} disabled={data.missing_students === 0}>
              {t('Напомнить всем, у кого не хватает')}
            </Button>
          </>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <StatRow>
        {data.counts.map((count) => (
          <StatCard
            key={count.code}
            icon="doc"
            tone={count.collected === count.total ? 'ok' : 'brand'}
            label={t(count.title)}
            value={`${count.collected} / ${count.total}`}
            onClick={() => setFilter('missing')}
          />
        ))}
      </StatRow>

      <div className="cfilters">
        {FILTERS.map((item) => (
          <button
            key={item.code}
            type="button"
            className={`cchip${filter === item.code ? ' cchip--on' : ''}`}
            onClick={() => setFilter(item.code)}
          >
            {t(item.label)}
            {item.code && (
              <span className="cchip__note">{data.filters[item.code as keyof typeof data.filters]}</span>
            )}
          </button>
        ))}
        <span className="cfilters__spacer" />
        <span className="muted cdocs__legend">
          {Object.entries(MARK).map(([state, mark]) => (
            <span key={state}>
              <span className={`cdocs__cell cdocs__cell--${state}`}>{mark}</span> {t(STATE_TITLE[state])}
            </span>
          ))}
          <span>
            <span className="cdocs__cell cdocs__cell--confirmed">{LINK_MARK}</span> {t('внешняя ссылка')}
          </span>
        </span>
      </div>

      <div className="card card-pad">
        <div className="tblwrap">
          <table className="tbl cdocs">
            <colgroup>
              <col style={{ width: '28%' }} />
              <col style={{ width: '12%' }} />
              {data.types.map((type) => (
                <col key={type.code} style={{ width: '10%' }} />
              ))}
              <col style={{ width: '10%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>{t('Ученик')}</th>
                <th>{t('Группа')}</th>
                {data.types.map((type) => (
                  <th key={type.code} title={t(type.title)}>
                    {t(type.title)}
                  </th>
                ))}
                <th className="r">{t('Собрано')}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.id}>
                  <td data-head="">
                    <a className="cdocs__name" href={`/students/${row.id}?tab=documents`}>
                      {row.full_name}
                    </a>
                  </td>
                  <td data-label={t('Группа')}>{row.group}</td>
                  {row.cells.map((cell, index) => {
                    const title = data.types[index]?.title ?? cell.code
                    return (
                      <td key={cell.code} data-label={t(title)}>
                        <button
                          type="button"
                          className={`cdocs__cell cdocs__cell--${cell.state}`}
                          title={`${t(title)}: ${t(STATE_TITLE[cell.state])}${
                            cell.is_link ? ` · ${t('внешняя ссылка')}` : ''
                          }`}
                          aria-label={`${row.full_name}, ${t(title)}: ${t(STATE_TITLE[cell.state])}`}
                          onClick={() => openCell(row, cell, title)}
                        >
                          {cell.is_link ? LINK_MARK : MARK[cell.state]}
                        </button>
                      </td>
                    )
                  })}
                  <td data-label={t('Собрано')} className="r num">
                    {row.collected} / {row.total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.results.length === 0 && <p className="muted">{t('По этому фильтру никого')}</p>}
      </div>

      {preview && <DocumentPreview target={preview} onClose={() => setPreview(null)} />}

      {letter && <LetterDialog target={letter} onClose={() => setLetter(null)} />}

      {remindAll && (
        <Modal title={t('Напомнить о документах')} onClose={() => setRemindAll(false)}>
          <div className="ctask">
            <p>
              {t('Учеников без полного набора:')} <b className="num">{data.missing_students}</b>.{' '}
              {t('Каждому уйдёт задача со списком именно его недостающих, срок — 7 дней.')}
            </p>
            <p className="cnote">{t('Задача видна ученику в календаре и на его доске.')}</p>
            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setRemindAll(false)}>
                {t('Отмена')}
              </Button>
              <Button
                disabled={remind.isPending}
                onClick={() =>
                  remind.mutate(
                    {},
                    {
                      onSuccess: (result) => {
                        toast.success(`${t('Задача отправлена ученикам:')} ${result.created}`)
                        setRemindAll(false)
                      },
                      onError: (e) => toast.error(e.message),
                    },
                  )
                }
              >
                {t('Отправить')} {data.missing_students}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

type DocumentsMatrixRow = {
  id: number
  full_name: string
  group: string
  collected: number
  total: number
  cells: DocumentCell[]
}
