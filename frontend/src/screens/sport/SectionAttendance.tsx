/**
 * «Посещаемость секций» — директор спорта и администратор (макет SAttendance, 27.10.2026).
 *
 * Фильтр — секция, час и месяц. Показатели месяца: среднее посещение,
 * сколько занятий прошло, сколько учеников ниже порога (настройка школы),
 * сколько отметок поставлено вручную. Таблица — ученики × даты занятий:
 * был по QR, вручную, не был. Пропуск — нет отметки на прошедшем занятии.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import { useSectionAttendance, type AttendanceData, type MarkCell } from '../../api/sport'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import { StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDayMonthShort, formatMonthYear } from '../../lib/format'
import { usePhone } from '../../phone'
import { slotWords } from './words'
import '../directors/directors.css'
import './sport.css'

const CELL: Record<Exclude<MarkCell, ''>, { label: string; tone: Tone }> = {
  qr: { label: tk('был'), tone: 'good' },
  manual: { label: tk('вручную'), tone: 'info' },
  absent: { label: tk('нет'), tone: 'bad' },
}

function thisMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/** Последние шесть месяцев учебного года: с сентября по текущий. */
function months(): string[] {
  const now = new Date()
  const out: string[] = []
  for (let back = 0; back < 6; back += 1) {
    const date = new Date(now.getFullYear(), now.getMonth() - back, 1)
    out.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`)
  }
  return out
}

export default function SectionAttendance() {
  const phone = usePhone()
  const [section, setSection] = useState<number | null>(null)
  const [slot, setSlot] = useState<number | null>(null)
  const [month, setMonth] = useState(thisMonth())
  const { data, isLoading, error } = useSectionAttendance({ section, slot, month })
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const current = data.sections.find((row) => row.id === data.section)
  const download = () => {
    const query = new URLSearchParams({ month: data.month, section: String(data.section) })
    downloadFile(`/sport/attendance/export/?${query.toString()}`, t('Посещаемость секций.xlsx'))
      .then(() => toast.success(t('Файл xlsx скачан · лист на каждое занятие')))
      .catch((reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason)))
  }
  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Посещаемость секций')}
        subtitle={t('Отметки по QR и вручную · видят директор спорта, администратор и куратор своей группы')}
        actions={
          <Button variant="outline" onClick={download}>
            {t('Скачать Excel')}
          </Button>
        }
      />
      <div className="filters">
        <Field
          kind="select"
          name="section"
          label={t('Секция')}
          value={String(data.section)}
          onChange={(value) => {
            setSection(Number(value))
            setSlot(null)
          }}
          options={data.sections.map((row) => ({ value: String(row.id), title: row.title }))}
        />
        <Field
          kind="select"
          className="sport-filter-wide"
          name="slot"
          label={t('Занятие')}
          value={String(data.slot.id)}
          onChange={(value) => setSlot(Number(value))}
          options={(current?.slots ?? []).map((row) => ({
            value: String(row.id),
            title: `${slotWords(row)} · ${row.parallel_from}–${row.parallel_to}`,
          }))}
        />
        <Field
          kind="select"
          name="month"
          label={t('Месяц')}
          value={data.month}
          onChange={setMonth}
          options={months().map((value) => ({ value, title: formatMonthYear(`${value}-01`) }))}
        />
      </div>
      <StatRow>
        <Kpi
          label={t('Среднее посещение')}
          value={data.figures.average === null ? null : `${data.figures.average}%`}
          none={t('нет занятий')}
        />
        <Kpi
          label={t('Занятий в месяце')}
          value={data.figures.sessions}
          note={t('из {n} по расписанию', { n: data.figures.sessions_total })}
        />
        <Kpi
          label={t('Ниже {n}%', { n: data.figures.threshold })}
          value={data.figures.below}
          tone={data.figures.below > 0 ? 'warn' : undefined}
          note={data.figures.below > 0 ? t('пропускают секцию') : undefined}
        />
        <Kpi label={t('Отмечено вручную')} value={data.figures.manual} />
      </StatRow>
      <DataCard
        title={`${current?.title ?? ''} · ${slotWords(data.slot)}`}
        note={t('параллели {grades} · {month}', {
          grades: `${data.slot.parallel_from}–${data.slot.parallel_to}`,
          month: formatMonthYear(`${data.month}-01`),
        })}
        count={data.rows.length}
        empty={data.rows.length === 0 && t('на этот час никто не записан')}
      >
        <DataTable
          columns={columns(data, phone)}
          rows={data.rows}
          rowKey={(row) => row.student.id}
          minWidth={phone ? undefined : `${360 + data.dates.length * 88}px`}
        />
      </DataCard>
    </div>
  )
}

function columns(data: AttendanceData, phone: boolean): Column<AttendanceData['rows'][number]>[] {
  return [
    {
      key: 'name',
      title: t('Ученик'),
      width: '220px',
      phone: 'head',
      cell: (row) => (
        <>
          <b className="dir__name">{row.student.short_name}</b>
          <span className="t-note dir__sub">
            {[t('{n} параллель', { n: row.student.parallel }), row.student.group].join(' · ')}
          </span>
        </>
      ),
    },
    ...data.dates.map((date, index) => ({
      key: date,
      title: formatDayMonthShort(date),
      width: '88px',
      phone: phone ? ('hidden' as const) : undefined,
      cell: (row: AttendanceData['rows'][number]) => {
        const cell = row.cells[index]
        return cell ? (
          <Chip tone={CELL[cell].tone} size="sm">
            {t(CELL[cell].label)}
          </Chip>
        ) : null
      },
    })),
    {
      key: 'percent',
      title: t('Посещение'),
      width: '180px',
      align: 'right',
      cell: (row) =>
        row.percent === null ? (
          <span className="t-note">{t('нет занятий')}</span>
        ) : (
          <span className="sport-pct">
            <span className="num">{row.percent}%</span>
            {row.below && (
              <Chip tone="warn" size="sm">
                {t('ниже порога')}
              </Chip>
            )}
          </span>
        ),
    },
  ]
}
