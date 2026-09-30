/**
 * Отчёты родителям: список по группе и периоду со статусами, отметка строк
 * и действия «для всех выбранных» — проверено, обновить данные, скачать
 * архивом, отправлены родителям; отчёт на одного ученика за выбранный
 * период; в отчёте — слово, кто его написал и когда (решение владельца,
 * 27.09.2026).
 *
 * Делают четыре роли: куратор по своим группам, Кымбат, Салтанат
 * и администратор по всем. Черновик не скачивается: сначала «Проверено».
 * Писем родителям сервер не шлёт — PDF уходит из мессенджера, поэтому
 * рядом телефон и текст с копированием; на телефоне — «Поделиться».
 *
 * Отчёты по шаблонам школы (30.09.2026): вариант 1 и 2, язык, период
 * «с — по»; тексты пишет ИИ черновиком, правит куратор; файл — PDF или
 * Word, архив группы собирается в очереди.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { fetchFile, saveBlob } from '../../api/client'
import {
  reportTone,
  useBuildReports,
  useReportsExport,
  useStartReportsExport,
  useCheckReport,
  useRefreshReport,
  useReport,
  useReports,
  useReportsCheck,
  useReportsRefresh,
  useReportSent,
  useReportsSent,
  useSaveReportWord,
  type ReportDetail,
  type ReportRow,
  type ReportStatus,
} from '../../api/academics'
import { useStudents } from '../../api/hooks'
import BuildReportDialog, { choiceInput, defaultChoice, ReportChoiceFields, type ReportChoice } from '../../components/BuildReportDialog'
import DataTable, { type Column } from '../../components/DataTable'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import { t } from '../../i18n'
import { usePhone } from '../../phone'
import SchoolReport from './SchoolReport'
import { GroupPick } from './shared'

type StatusFilter = ReportStatus | 'all'

type MarkLine = { key: number; title: string; value: string; note: string }

/** «сейчас выходит 3» и «итог 4» — число в колонке «Итог», слово — рядом с ФО и СОР. */
function finalOf(value: string): { mark: string; word: string } {
  const found = value.match(/^(.*?)(\d+)$/)
  if (!found) return { mark: '', word: value }
  return { mark: found[2], word: found[1].trim() }
}

const MARK_COLUMNS: Column<MarkLine>[] = [
  { key: 'subject', title: t('Предмет'), width: '38%', cell: (line) => <b>{line.title}</b> },
  { key: 'parts', title: t('ФО, СОР, СОЧ'), width: '46%', cell: (line) => <span className="num">{line.note || finalOf(line.value).word || t('нет')}</span> },
  { key: 'final', title: t('Итог'), width: '16%', align: 'right', cell: (line) => (finalOf(line.value).mark ? <b className="num">{finalOf(line.value).mark}</b> : <span className="t-note">{t('нет')}</span>) },
]

const when = (value: string | null) => (value ? new Date(value).toLocaleDateString('ru') : '')
const whenAt = (value: string | null) => (value ? new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' }) : '')

async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(done)
  } catch {
    toast.error(t('Не удалось скопировать: выделите текст и скопируйте руками'))
  }
}

type FileType = 'pdf' | 'docx'

const FILE_MIME: Record<FileType, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

/** Файл отчёта (PDF или Word): скачать, а на телефоне — отдать в «Поделиться», если умеет. */
async function takeFile(report: ReportRow, type: FileType, share: boolean): Promise<'shared' | 'saved'> {
  const file = await fetchFile(`/acad/reports/${report.id}/pdf/?type=${type}`, `${report.student.full_name}.${type}`)
  if (share && typeof navigator.canShare === 'function') {
    const pdf = new File([file.blob], file.name, { type: FILE_MIME[type] })
    if (navigator.canShare({ files: [pdf] })) {
      await navigator.share({ files: [pdf], title: file.name.replace(/\.pdf$/i, '') })
      return 'shared'
    }
  }
  saveBlob(file.blob, file.name)
  return 'saved'
}

export default function Reports() {
  const phone = usePhone()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const group = params.get('group') ?? 'all'
  const period = params.get('period') ?? ''
  const status = (params.get('status') ?? 'all') as StatusFilter
  const open = params.get('open')
  const set = (patch: Record<string, string>) => {
    const updated = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value && value !== 'all') updated.set(key, value)
      else updated.delete(key)
    }
    setParams(updated, { replace: true })
  }
  const list = useReports({ group: group === 'all' ? '' : group, period, status: status === 'all' ? '' : status })
  const sentMany = useReportsSent()
  const checkMany = useReportsCheck()
  const refreshMany = useReportsRefresh()
  const [checked, setChecked] = useState<number[]>([])
  const [building, setBuilding] = useState<'group' | 'student' | null>(null)
  const [exporting, setExporting] = useState<{ ids: number[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const fail = (e: Error) => toast.error(e.message)

  // выбор сбрасывается вместе с периодом и группой: отмечали одни строки, показаны другие
  useEffect(() => setChecked([]), [group, period, status])

  if (list.isLoading && !list.data) return <Loading kind="table" />
  if (list.error) return <ErrorNote error={list.error} />
  if (!list.data) return null
  const data = list.data
  const rows = data.rows
  const ready = rows.filter((row) => row.status !== 'draft')
  const readyChecked = checked.filter((id) => ready.some((row) => row.id === id))
  const openRow = open ? Number(open) : null

  const zip = async (ids: number[]) => {
    // шаблоны школы — PDF или Word, архив собирает очередь; стандартный — как раньше
    if (data.period && data.period.template !== 'standard') {
      setExporting({ ids })
      return
    }
    setBusy(true)
    try {
      const tail = ids.length
        ? `ids=${ids.join(',')}`
        : `group=${encodeURIComponent(group === 'all' ? '' : group)}&period=${encodeURIComponent(data.period?.code ?? '')}`
      const file = await fetchFile(`/acad/reports/zip/?${tail}`, 'отчёты.zip')
      saveBlob(file.blob, file.name)
      toast.success(t('Архив скачан: проверенные отчёты помечены выгруженными'))
      void list.refetch()
    } catch (e) {
      fail(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const columns: Column<ReportRow>[] = [
    {
      key: 'pick',
      title: '',
      width: '5%',
      cell: (row) => (
        <Checkbox
          aria-label={`${t('Отметить')}: ${row.student.full_name}`}
          checked={checked.includes(row.id)}
          onCheckedChange={(value) => setChecked((old) => (value ? [...old, row.id] : old.filter((id) => id !== row.id)))}
        />
      ),
    },
    {
      key: 'student',
      title: t('Ученик'),
      width: '27%',
      cell: (row) => (
        <>
          <b>{row.student.full_name}</b>
          <span className="t-note"> · {row.student.group}</span>
        </>
      ),
      sortBy: (row) => row.student.full_name,
    },
    { key: 'att', title: t('Посещаемость'), width: '14%', align: 'right', cell: (row) => <span className="num">{row.attendance || t('нет')}</span>, sortBy: (row) => row.attendance },
    { key: 'grades', title: t('Оценки'), width: '18%', cell: (row) => <Chip tone={row.grades.tone as Tone} size="sm">{t(row.grades.text)}</Chip> },
    {
      key: 'phone',
      title: t('Телефон'),
      width: '16%',
      cell: (row) => (row.phones[0] ? <span className="num">{row.phones[0].phone}</span> : <span className="t-note">{t('нет контакта')}</span>),
    },
    {
      key: 'status',
      title: t('Статус'),
      width: '20%',
      cell: (row) => (
        <>
          <Chip tone={reportTone(row.status)} size="sm">
            {t(row.status_title)}
          </Chip>
          {row.sent_at && <span className="t-note"> {when(row.sent_at)}</span>}
        </>
      ),
      sortBy: (row) => row.status,
    },
  ]

  const statusItems: { value: StatusFilter; label: string }[] = [
    { value: 'all', label: `${t('Все')} ${data.counts.total}` },
    ...data.statuses.map((row) => ({ value: row.code, label: `${t(row.title)} ${data.counts[row.code] ?? 0}` })),
  ]

  const allChecked = rows.length > 0 && checked.length === rows.length

  return (
    <div>
      <ScreenHead
        title={t('Отчёты родителям')}
        subtitle={`${t('Собираются')} ${t(data.cadence)}`}
        actions={
          <>
            {ready.length > 0 && (
              <Button size="sm" disabled={busy} onClick={() => void zip([])}>
                {t('Скачать все')}
              </Button>
            )}
            {data.may_build && (
              <RowMenu>
                <RowMenuItem onClick={() => setBuilding('group')}>{t('Собрать за период')}</RowMenuItem>
                <RowMenuItem onClick={() => setBuilding('student')}>{t('Собрать по ученику')}</RowMenuItem>
              </RowMenu>
            )}
          </>
        }
      />
      <div className="acad__toolbar">
        <GroupPick groups={data.groups} value={group} onChange={(code) => set({ group: code })} all={t('Все группы')} />
        {data.periods.length > 0 && (
          <Segmented
            value={data.period?.code ?? ''}
            onChange={(code) => set({ period: code })}
            label={t('Период')}
            items={data.periods.map((row) => ({ value: row.code, label: t(row.title) }))}
          />
        )}
      </div>

      {!data.period && (
        <DataCard
          title={t('Отчётов ещё нет')}
          empty={`${t('соберутся сами')} ${t(data.cadence)}`}
          emptyAction={
            data.may_build ? (
              <Button variant="secondary" size="sm" onClick={() => setBuilding('group')}>
                {t('Собрать сейчас')}
              </Button>
            ) : undefined
          }
        />
      )}

      {data.period && (
        <div className="acad__stack">
          <StatRow>
            <Kpi label={t('Всего')} value={data.counts.total} note={t(data.period.title)} />
            <Kpi label={t('Черновики')} value={data.counts.draft || null} none={t('нет')} tone={data.counts.draft ? 'warn' : undefined} />
            <Kpi label={t('Проверены')} value={data.counts.checked || null} none={t('нет')} tone={data.counts.checked ? 'info' : undefined} />
            <Kpi label={t('Выгружены')} value={data.counts.exported || null} none={t('нет')} />
            <Kpi label={t('Отправлены')} value={data.counts.sent || null} none={t('нет')} tone={data.counts.sent === data.counts.total && data.counts.total ? 'good' : undefined} note={data.counts.no_phone ? `${t('без телефона')} ${data.counts.no_phone}` : undefined} />
          </StatRow>
          <div className="acad__toolbar">
            <Segmented<StatusFilter> value={status} onChange={(next) => set({ status: next })} label={t('Статус')} items={statusItems} />
            {data.built_at && <span className="t-note">{`${t('собрано')} ${when(data.built_at)}`}</span>}
          </div>
          {/* действия для всех отмеченных: проверено, обновить, архивом, отправлены */}
          {checked.length > 0 && data.may_write && (
            <DataCard title={`${t('Отмечено:')} ${checked.length}`}>
              <div className="acad__actions">
                <Button variant="outline" size="sm" disabled={checkMany.isPending} onClick={() => checkMany.mutate(checked, { onSuccess: (r) => toast.success(`${t('Проверено:')} ${r.checked}`), onError: fail })}>
                  {t('Проверено')}
                </Button>
                <Button variant="outline" size="sm" disabled={refreshMany.isPending} onClick={() => refreshMany.mutate(checked, { onSuccess: (r) => toast.success(`${t('Обновлено:')} ${r.refreshed} · ${t('изменилось')} ${r.changed}`), onError: fail })}>
                  {t('Обновить данные')}
                </Button>
                <Button variant="outline" size="sm" disabled={busy || readyChecked.length === 0} onClick={() => void zip(readyChecked)}>
                  {t('Скачать архивом')} ({readyChecked.length})
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={sentMany.isPending || readyChecked.length === 0}
                  onClick={() =>
                    sentMany.mutate(readyChecked, {
                      onSuccess: (r) => {
                        toast.success(`${t('Отмечено отправленными:')} ${r.sent}${r.skipped.length ? ` · ${t('пропущено')}: ${r.skipped.join(', ')}` : ''}`)
                        setChecked([])
                      },
                      onError: fail,
                    })
                  }
                >
                  {t('Отправлены родителям')} ({readyChecked.length})
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setChecked([])}>
                  {t('Снять отметки')}
                </Button>
              </div>
            </DataCard>
          )}
          <DataCard
            title={t(data.period.title)}
            count={rows.length || undefined}
            right={
              rows.length > 0 ? (
                <Button variant="link" size="sm" onClick={() => setChecked(allChecked ? [] : rows.map((row) => row.id))}>
                  {allChecked ? t('Снять все') : t('Отметить все')}
                </Button>
              ) : undefined
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => set({ open: String(row.id) })} selected={(row) => row.id === openRow || checked.includes(row.id)} empty={<span className="t-note">{t('с таким статусом отчётов нет')}</span>} minWidth="820px" />
          </DataCard>
        </div>
      )}

      {openRow !== null && <ReportDrawer id={openRow} phone={phone} onClose={() => set({ open: '' })} onStudent={(id) => navigate(`/students/${id}`)} />}
      {building === 'group' && <BuildDialog periods={data.periods} groups={data.groups} group={group} onClose={() => setBuilding(null)} onBuilt={(code) => code && set({ period: code })} />}
      {exporting && data.period && (
        <ExportDialog
          ids={exporting.ids}
          group={group === 'all' ? '' : group}
          period={data.period.code}
          onClose={() => {
            setExporting(null)
            void list.refetch()
          }}
        />
      )}
      {building === 'student' && <PickStudentDialog groups={data.groups} group={group} onClose={() => setBuilding(null)} />}
    </div>
  )
}

function ReportDrawer({ id, phone, onClose, onStudent }: { id: number; phone: boolean; onClose: () => void; onStudent: (student: number) => void }) {
  const report = useReport(id)
  // черновик ИИ пишется в очереди — панель переспрашивает, пока он не готов
  const pending = report.data?.school?.draft.state === 'pending'
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => void report.refetch(), 3000)
    return () => window.clearInterval(timer)
  }, [pending, report])
  const saveWord = useSaveReportWord()
  const check = useCheckReport()
  const refresh = useRefreshReport()
  const sent = useReportSent()
  const [word, setWord] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (report.data) setWord(report.data.curator_word)
  }, [report.data])
  const fail = (e: Error) => toast.error(e.message)
  const data = report.data

  const download = async (row: ReportDetail, share: boolean, type: FileType = 'pdf') => {
    setBusy(true)
    try {
      const outcome = await takeFile(row, type, share)
      toast.success(outcome === 'shared' ? t('Отчёт передан в «Поделиться»') : type === 'pdf' ? t('PDF скачан') : t('Word скачан'))
      void report.refetch()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') fail(e as Error)
    } finally {
      setBusy(false)
    }
  }
  const checkAndDownload = (row: ReportDetail, type: FileType = 'pdf') =>
    check.mutate(
      { id: row.id, curator_word: row.word_on && !row.school ? word : undefined },
      { onSuccess: (fresh) => void download(fresh, phone, type), onError: fail },
    )

  const editable = Boolean(data?.may_write) && data?.status !== 'sent'
  const wordChanged = data ? word.trim() !== data.curator_word.trim() : false
  const wordBy = data?.word_by ? `${data.word_by}${data.word_at ? ` · ${whenAt(data.word_at)}` : ''}` : ''

  return (
    <EditDrawer
      open
      onClose={onClose}
      className="drawer--wide"
      title={data ? data.student.full_name : t('Отчёт')}
      sub={data ? `${t(data.title)} · ${data.student.group} · ${t(data.status_title)}` : undefined}
      footer={
        data ? (
          <>
            {data.status === 'draft' && data.may_write && data.formats.map((type) => (
              <Button key={type} variant={type === 'pdf' ? 'default' : 'outline'} disabled={busy || check.isPending} onClick={() => checkAndDownload(data, type)}>
                {type === 'pdf' ? t('Проверено и скачать PDF') : t('Проверено и скачать Word')}
              </Button>
            ))}
            {data.status !== 'draft' && data.formats.map((type) => (
              <Button key={type} variant={type === 'pdf' ? 'default' : 'outline'} disabled={busy} onClick={() => void download(data, phone, type)}>
                {phone ? `${t('Поделиться')} ${type === 'pdf' ? 'PDF' : 'Word'}` : type === 'pdf' ? t('Скачать PDF') : t('Скачать Word')}
              </Button>
            ))}
            {data.status !== 'draft' && phone && (
              <Button variant="outline" disabled={busy} onClick={() => void download(data, false)}>
                {t('Скачать PDF')}
              </Button>
            )}
            {data.may_write && (
              <Button
                variant="outline"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate(data.id, { onSuccess: (fresh) => toast.success(fresh.changed ? t('Данные обновлены: отчёт снова черновик') : t('Ничего не изменилось')), onError: fail })}
              >
                {t('Обновить данные')}
              </Button>
            )}
          </>
        ) : undefined
      }
    >
      {report.isLoading && !data && <Loading kind="cards" />}
      {report.error && <ErrorNote error={report.error} />}
      {data && (
        <>
          {(data.checked_at || data.exported_at || data.sent_at) && (
            <Rows>
              <Row icon="report" tone={reportTone(data.status) as Tone} title={[data.checked_at ? `${t('проверен')} ${when(data.checked_at)} ${data.checked_by}` : '', data.exported_at ? `${t('выгружен')} ${when(data.exported_at)}` : '', data.sent_at ? `${t('отправлен')} ${when(data.sent_at)} ${data.sent_by}` : ''].filter(Boolean).join(' · ')} />
            </Rows>
          )}
          {data.school && <SchoolReport report={data} editable={editable} />}
          {!data.school && data.sections.map((section) =>
            section.code === 'grades' ? (
              <DataCard key={section.code} title={t(section.title)}>
                <DataTable columns={MARK_COLUMNS} rows={section.lines.map((line, index) => ({ ...line, key: index }))} rowKey={(line) => line.key} />
              </DataCard>
            ) : (
              <DataCard key={section.code} title={t(section.title)}>
                <Rows>
                  {section.lines.map((line, index) => (
                    <Row key={`${section.code}-${index}`} title={line.title} note={line.note || undefined} value={line.value} none={t('нет')} />
                  ))}
                </Rows>
              </DataCard>
            ),
          )}
          {/* раздел «Слово куратора» выключен в настройках отчётов — блока нет, в PDF слова нет */}
          {data.word_on && !data.school && (editable ? (
            <>
              <Field kind="textarea" name="curator_word" label={t('Слово куратора')} value={word} onChange={setWord} rows={4} hint={wordBy || undefined} />
              {wordChanged && data.status !== 'draft' && (
                <Button variant="outline" size="sm" disabled={saveWord.isPending} onClick={() => saveWord.mutate({ id: data.id, curator_word: word }, { onSuccess: () => toast.success(t('Слово сохранено')), onError: fail })}>
                  {t('Сохранить слово')}
                </Button>
              )}
            </>
          ) : (
            <Rows>
              <Row title={t('Слово куратора')} note={wordBy || undefined} value={data.curator_word || null} none={t('нет')} />
            </Rows>
          ))}
          <DataCard title={t('Родителям')}>
            {data.phones.length === 0 && (
              <Rows>
                <Row icon="person" tone="warn" title={t('Телефона родителя нет')} acts={<Button variant="secondary" size="sm" onClick={() => onStudent(data.student.id)}>{t('Добавить контакт')}</Button>} />
              </Rows>
            )}
            <Rows>
              {data.phones.map((phoneRow) => (
                <Row
                  key={`${phoneRow.phone}-${phoneRow.name}`}
                  icon="phone"
                  title={phoneRow.phone}
                  note={`${phoneRow.name} · ${phoneRow.relation}${phoneRow.is_primary ? ` · ${t('основной')}` : ''}`}
                  acts={<Button variant="secondary" size="sm" onClick={() => void copyText(phoneRow.phone, t('Телефон скопирован'))}>{t('Скопировать')}</Button>}
                />
              ))}
            </Rows>
            <Field kind="textarea" name="message" label={t('Текст сообщения')} value={data.message} rows={3} readOnly />
            <div className="acad__actions">
              <Button variant="outline" size="sm" onClick={() => void copyText(data.message, t('Текст скопирован'))}>
                {t('Скопировать текст')}
              </Button>
              {data.may_write && data.status !== 'draft' && (
                <Button
                  variant={data.status === 'sent' ? 'outline' : 'secondary'}
                  size="sm"
                  disabled={sent.isPending}
                  onClick={() => sent.mutate({ id: data.id, sent: data.status !== 'sent' }, { onSuccess: () => toast.success(data.status === 'sent' ? t('Отметка снята') : t('Отмечен отправленным родителям')), onError: fail })}
                >
                  {data.status === 'sent' ? t('Снять отметку «отправлен»') : t('Отправлен родителям')}
                </Button>
              )}
            </div>
          </DataCard>
        </>
      )}
    </EditDrawer>
  )
}

/** Собрать отчёты за период по группе или по всем — стандартные обычно собирает расписание. */
function BuildDialog({ periods, groups, group, onClose, onBuilt }: { periods: { code: string; title: string; kind: string }[]; groups: { id: number; code: string }[]; group: string; onClose: () => void; onBuilt: (period: string) => void }) {
  const build = useBuildReports()
  const [choice, setChoice] = useState<ReportChoice>(defaultChoice)
  const [picked, setPicked] = useState(group)
  const built = new Set(periods.map((row) => row.code))
  const mark = (value: string, title: string) => (built.has(`standard:ru:month:${value}-01:`) ? `${title} · ${t('уже собран')}` : title)
  return (
    <Modal title={t('Собрать отчёты за период')} onClose={onClose}>
      <ReportChoiceFields value={choice} onChange={setChoice} mark={mark} />
      <Field kind="select" name="group" label={t('Группа')} value={picked} onChange={setPicked} options={[{ value: 'all', title: t('Все группы') }, ...groups.map((row) => ({ value: row.code, title: row.code }))]} />
      <div className="acad__actions">
        <Button
          disabled={build.isPending}
          onClick={() =>
            build.mutate(
              { ...choiceInput(choice), group: picked === 'all' ? '' : picked },
              {
                onSuccess: (r) => {
                  toast.success(`${t('Собрано отчётов:')} ${counted(r.built, ['отчёт', 'отчёта', 'отчётов'])} · ${t(r.title)}`)
                  onBuilt(r.period)
                  onClose()
                },
                onError: (e) => toast.error(e.message),
              },
            )
          }
        >
          {t('Собрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Архив отчётов по шаблону школы: формат, сборка в очереди с ходом, скачивание. */
function ExportDialog({ ids, group, period, onClose }: { ids: number[]; group: string; period: string; onClose: () => void }) {
  const start = useStartReportsExport()
  const [type, setType] = useState<FileType>('pdf')
  const [job, setJob] = useState<string | null>(null)
  const state = useReportsExport(job)
  const [saved, setSaved] = useState(false)
  const done = state.data?.state === 'done'
  useEffect(() => {
    if (!done || saved || !job) return
    setSaved(true)
    fetchFile(`/acad/reports/export/${job}/file/`, state.data?.name || 'отчёты.zip')
      .then((file) => {
        saveBlob(file.blob, file.name)
        toast.success(t('Архив скачан: отчёты помечены выгруженными'))
        onClose()
      })
      .catch((e: Error) => toast.error(e.message))
  }, [done, saved, job, state.data, onClose])
  return (
    <Modal title={t('Скачать архивом')} note={ids.length ? `${t('Отмечено:')} ${ids.length}` : t('Все проверенные отчёты периода')} onClose={onClose}>
      {!job && (
        <>
          <Segmented<FileType> value={type} onChange={setType} label={t('Формат')} items={[{ value: 'pdf', label: 'PDF' }, { value: 'docx', label: 'Word' }]} />
          <div className="acad__actions">
            <Button
              disabled={start.isPending}
              onClick={() =>
                start.mutate(ids.length ? { ids, format: type } : { group, period, format: type }, {
                  onSuccess: (r) => setJob(r.job),
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              {t('Собрать архив')}
            </Button>
            <Button variant="outline" onClick={onClose}>
              {t('Отмена')}
            </Button>
          </div>
        </>
      )}
      {job && (
        <Rows>
          <Row
            icon={state.data?.state === 'failed' ? 'alert' : 'download'}
            tone={state.data?.state === 'failed' ? 'bad' : undefined}
            title={
              state.data?.state === 'failed'
                ? t(state.data.error || 'Архив не собрался')
                : `${t('Собирается архив')}: ${state.data?.done ?? 0} ${t('из')} ${state.data?.total ?? ids.length}`
            }
            note={type === 'pdf' ? t('PDF для группы собирается до минуты') : undefined}
          />
        </Rows>
      )}
    </Modal>
  )
}

/** Отчёт по одному ученику: сначала группа и ученик, потом период. */
function PickStudentDialog({ groups, group, onClose }: { groups: { id: number; code: string }[]; group: string; onClose: () => void }) {
  const [picked, setPicked] = useState(group === 'all' ? (groups[0]?.code ?? '') : group)
  const found = groups.find((row) => row.code === picked)
  const students = useStudents({ group: found ? String(found.id) : '', page_size: 200 })
  const rows = students.data?.results ?? []
  const [student, setStudent] = useState<string>('')
  const chosen = rows.find((row) => String(row.id) === student)
  if (chosen) return <BuildReportDialog student={chosen.id} studentName={chosen.full_name} onClose={onClose} />
  return (
    <Modal title={t('Отчёт по ученику')} onClose={onClose}>
      <Field
        kind="select"
        name="group"
        label={t('Группа')}
        value={picked}
        onChange={(value) => {
          setPicked(value)
          setStudent('')
        }}
        options={groups.map((row) => ({ value: row.code, title: row.code }))}
      />
      {students.isLoading ? (
        <Loading />
      ) : (
        <Field kind="select" name="student" label={t('Ученик')} value={student} onChange={setStudent} options={[{ value: '', title: t('выберите ученика') }, ...rows.map((row) => ({ value: String(row.id), title: row.full_name }))]} />
      )}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
