/**
 * Отчёты родителям: список по группе и периоду со статусами, проверка,
 * слово куратора, PDF и ZIP, «Поделиться» на телефоне, телефон родителя
 * и текст сообщения, отметка «отправлен родителям» по одному и списком.
 *
 * Куратор проверяет и отправляет; Кымбат и администратор читают, скачивают
 * и собирают отчёты руками (обычно их собирает расписание). Черновик не
 * скачивается: сначала «Проверено и скачать». Писем родителям сервер не шлёт —
 * PDF уходит из мессенджера куратора, поэтому рядом телефон и текст с копированием.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { fetchFile, saveBlob } from '../../api/client'
import {
  reportTone,
  useBuildReports,
  useCheckReport,
  useRefreshReport,
  useReport,
  useReports,
  useReportSent,
  useReportsSent,
  useSaveReportWord,
  type ReportDetail,
  type ReportRow,
  type ReportStatus,
} from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import { t } from '../../i18n'
import { usePhone } from '../../phone'
import { GroupPick, NoteCard } from './shared'

type StatusFilter = ReportStatus | 'all'

const when = (value: string | null) => (value ? new Date(value).toLocaleDateString('ru') : '')

async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(done)
  } catch {
    toast.error(t('Не удалось скопировать: выделите текст и скопируйте руками'))
  }
}

/** PDF отчёта: скачать, а на телефоне — отдать в «Поделиться», если умеет. */
async function takePdf(report: ReportRow, share: boolean): Promise<'shared' | 'saved'> {
  const file = await fetchFile(`/acad/reports/${report.id}/pdf/`, `${report.student.full_name}.pdf`)
  if (share && typeof navigator.canShare === 'function') {
    const pdf = new File([file.blob], file.name, { type: 'application/pdf' })
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
  const [checked, setChecked] = useState<number[]>([])
  const [building, setBuilding] = useState(false)
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

  return (
    <div>
      <ScreenHead
        title={t('Отчёты родителям')}
        subtitle={`${t('Собираются')} ${t(data.cadence)}. ${t('Куратор проверяет, скачивает и отправляет сам; писем родителям нет.')}`}
        actions={
          <>
            {data.may_build && (
              <Button variant="outline" size="sm" onClick={() => setBuilding(true)}>
                {t('Собрать за период')}
              </Button>
            )}
            {data.may_write && readyChecked.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                disabled={sentMany.isPending}
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
            )}
            {ready.length > 0 && (
              <Button size="sm" disabled={busy} onClick={() => void zip(readyChecked)}>
                {readyChecked.length ? `${t('Скачать отмеченные')} (${readyChecked.length})` : t('Скачать все')}
              </Button>
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
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Отчётов ещё нет')} empty={`${t('соберутся сами')} ${t(data.cadence)}`} emptyAction={data.may_build ? <Button variant="secondary" size="sm" onClick={() => setBuilding(true)}>{t('Собрать сейчас')}</Button> : undefined} />
          </div>
          <div className="acad__stack">
            <NoteCard title={t('Как это устроено')}>
              {t('Отчёт — снимок посещаемости, оценок, экзаменов и документов за период. Куратор читает его, пишет своё слово, нажимает «Проверено и скачать» и отправляет PDF родителям сам.')}
            </NoteCard>
          </div>
        </div>
      )}

      {data.period && (
        <>
          <StatRow>
            <Kpi label={t('Всего')} value={data.counts.total} note={t(data.period.title)} />
            <Kpi label={t('Черновики')} value={data.counts.draft || null} none={t('нет')} tone={data.counts.draft ? 'warn' : undefined} note={t('ждут проверки')} />
            <Kpi label={t('Проверены')} value={data.counts.checked || null} none={t('нет')} tone={data.counts.checked ? 'info' : undefined} />
            <Kpi label={t('Выгружены')} value={data.counts.exported || null} none={t('нет')} />
            <Kpi label={t('Отправлены')} value={data.counts.sent || null} none={t('нет')} tone={data.counts.sent === data.counts.total && data.counts.total ? 'good' : undefined} note={data.counts.no_phone ? `${t('без телефона')} ${data.counts.no_phone}` : undefined} />
          </StatRow>
          <div className="acad__toolbar">
            <Segmented<StatusFilter> value={status} onChange={(next) => set({ status: next })} label={t('Статус')} items={statusItems} />
            {data.built_at && <span className="t-note">{`${t('собрано')} ${when(data.built_at)}`}</span>}
          </div>
          <div className="card">
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => set({ open: String(row.id) })} selected={(row) => row.id === openRow} empty={<span className="t-note">{t('с таким статусом отчётов нет')}</span>} />
          </div>
          {phone && (
            <p className="t-note acad__note">{t('На телефоне PDF уходит в «Поделиться»: откройте отчёт.')}</p>
          )}
        </>
      )}

      {openRow !== null && <ReportDrawer id={openRow} phone={phone} onClose={() => set({ open: '' })} onStudent={(id) => navigate(`/students/${id}`)} />}
      {building && <BuildDialog periods={data.periods} groups={data.groups} group={group} onClose={() => setBuilding(false)} />}
    </div>
  )
}

function ReportDrawer({ id, phone, onClose, onStudent }: { id: number; phone: boolean; onClose: () => void; onStudent: (student: number) => void }) {
  const report = useReport(id)
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

  const download = async (row: ReportDetail, share: boolean) => {
    setBusy(true)
    try {
      const outcome = await takePdf(row, share)
      toast.success(outcome === 'shared' ? t('Отчёт передан в «Поделиться»') : t('PDF скачан'))
      void report.refetch()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') fail(e as Error)
    } finally {
      setBusy(false)
    }
  }
  const checkAndDownload = (row: ReportDetail) =>
    check.mutate({ id: row.id, curator_word: word }, { onSuccess: (fresh) => void download(fresh, phone), onError: fail })

  const editable = Boolean(data?.may_write) && data?.status !== 'sent'
  const wordChanged = data ? word.trim() !== data.curator_word.trim() : false

  return (
    <EditDrawer
      open
      onClose={onClose}
      title={data ? data.student.full_name : t('Отчёт')}
      sub={data ? `${t(data.title)} · ${data.student.group} · ${t(data.status_title)}` : undefined}
      footer={
        data ? (
          <>
            {data.status === 'draft' && data.may_write && (
              <Button disabled={busy || check.isPending} onClick={() => checkAndDownload(data)}>
                {t('Проверено и скачать')}
              </Button>
            )}
            {data.status !== 'draft' && (
              <Button disabled={busy} onClick={() => void download(data, phone)}>
                {phone ? t('Поделиться') : t('Скачать PDF')}
              </Button>
            )}
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
          <Rows>
            <Row icon="doc" tone={reportTone(data.status) as Tone} title={t(data.status_title)} note={[data.checked_at ? `${t('проверен')} ${when(data.checked_at)} ${data.checked_by}` : '', data.exported_at ? `${t('выгружен')} ${when(data.exported_at)}` : '', data.sent_at ? `${t('отправлен')} ${when(data.sent_at)} ${data.sent_by}` : ''].filter(Boolean).join(' · ') || t('черновик: проверьте и скачайте')} />
          </Rows>
          {data.sections.map((section) => (
            <DataCard key={section.code} title={t(section.title)}>
              <Rows>
                {section.lines.map((line, index) => (
                  <Row key={`${section.code}-${index}`} title={line.title} note={line.note || undefined} value={line.value} none={t('нет')} />
                ))}
              </Rows>
            </DataCard>
          ))}
          {editable ? (
            <>
              <Field kind="textarea" name="curator_word" label={t('Слово куратора')} value={word} onChange={setWord} rows={4} placeholder={t('Родители прочитают это в конце отчёта')} hint={t('Сохраняется вместе с «Проверено»; можно записать заранее.')} />
              {wordChanged && data.status !== 'draft' && (
                <Button variant="outline" size="sm" disabled={saveWord.isPending} onClick={() => saveWord.mutate({ id: data.id, curator_word: word }, { onSuccess: () => toast.success(t('Слово сохранено')), onError: fail })}>
                  {t('Сохранить слово')}
                </Button>
              )}
            </>
          ) : (
            <Field.Static label={t('Слово куратора')}>{data.curator_word || t('нет')}</Field.Static>
          )}
          <DataCard title={t('Родителям')} note={t('Телефон — основной первым; текст сообщения — рядом с PDF')}>
            {data.phones.length === 0 && (
              <Rows>
                <Row icon="person" tone="warn" title={t('Телефона родителя нет')} note={t('выгрузке это не мешает')} acts={<Button variant="secondary" size="sm" onClick={() => onStudent(data.student.id)}>{t('Добавить контакт')}</Button>} />
              </Rows>
            )}
            <Rows>
              {data.phones.map((phoneRow) => (
                <Row
                  key={`${phoneRow.phone}-${phoneRow.name}`}
                  icon="person"
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

/** Собрать отчёты руками — Кымбат и администратор; обычно это делает расписание. */
function BuildDialog({ periods, groups, group, onClose }: { periods: { code: string; title: string; kind: string }[]; groups: { id: number; code: string }[]; group: string; onClose: () => void }) {
  const build = useBuildReports()
  const today = new Date()
  const monthCode = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  const [period, setPeriod] = useState(monthCode)
  const [picked, setPicked] = useState(group)
  const previous = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const previousCode = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`
  const built = new Set(periods.map((row) => row.code))
  const mark = (kind: string, start: string, title: string) => (built.has(`${kind}:${start}`) ? `${title} · ${t('уже собран')}` : title)
  return (
    <Modal title={t('Собрать отчёты за период')} note={t('Готовые отчёты пересоберутся; статус откатится в черновик только там, где данные изменились')} onClose={onClose}>
      <Field
        kind="select"
        name="period"
        label={t('Период')}
        value={period}
        onChange={setPeriod}
        options={[
          { value: monthCode, title: mark('month', `${monthCode}-01`, `${t('текущий месяц')} · ${monthCode}`) },
          { value: previousCode, title: mark('month', `${previousCode}-01`, `${t('прошлый месяц')} · ${previousCode}`) },
          { value: 'q1', title: t('1 четверть') },
          { value: 'q2', title: t('2 четверть') },
          { value: 'q3', title: t('3 четверть') },
          { value: 'q4', title: t('4 четверть') },
        ]}
      />
      <Field kind="select" name="group" label={t('Группа')} value={picked} onChange={setPicked} options={[{ value: 'all', title: t('Все группы') }, ...groups.map((row) => ({ value: row.code, title: row.code }))]} />
      <div className="acad__actions">
        <Button
          disabled={build.isPending}
          onClick={() =>
            build.mutate(
              { period, group: picked === 'all' ? '' : picked },
              {
                onSuccess: (r) => {
                  toast.success(`${t('Собрано отчётов:')} ${counted(r.built, ['отчёт', 'отчёта', 'отчётов'])} · ${t(r.title)}`)
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
