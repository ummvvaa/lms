/**
 * Учебный год: четверти и каникулы, расписания звонков карточками — у
 * каждого свои группы, общего на всех нет (решение владельца, 05.10.2026);
 * группы без звонков названы строкой ошибки. Шкала
 * оценивания, настройки отчётов родителям, закрытие четверти.
 * Казахские названия предметов — для отчётов родителям на казахском (30.09.2026).
 *
 * Раскладка по макету (22.10.2026): ряд «четверти и каникулы» на две трети
 * с итогами четверти рядом; ряд из трёх карточек — шкала, отчёты родителям,
 * названия предметов; тихая строка «не назначены звонки»; звонки по четыре
 * в ряд, внутри время двумя столбцами; внизу таблица предметов. Каникулы —
 * подписью под своей четвертью, праздники — чипами под четвертями.
 * На телефоне — всё столбиком в том же порядке.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useCloseQuarter, useSaveYear, useSubjectInLms, useYear, type BellSchedule, type SubjectRow, type YearScreen } from '../../api/academics'
import { useStudyGroups } from '../../api/hooks'
import ConfirmDialog from '../../components/ConfirmDialog'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { SelectField } from '../../components/SelectField'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { dateShort, dateWords } from './shared'
import { todayAlmaty } from '../../lib/dates'

function QuartersDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [rows, setRows] = useState(year.quarters.map((q) => ({ ...q })))
  const [breaks, setBreaks] = useState(year.breaks.map((b) => ({ ...b })))
  const [error, setError] = useState('')
  const submit = () =>
    save.mutate(
      { quarters: rows.map((q) => ({ number: q.number, title: q.title, starts: q.starts, ends: q.ends })), breaks: breaks.map((b) => ({ title: b.title, starts: b.starts, ends: b.ends })) },
      {
        onSuccess: () => {
          toast.success(t('Четверти сохранены'))
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  return (
    <Modal title={t('Четверти и каникулы')} onClose={onClose} wide>
      {rows.map((q, i) => (
        <Field.Row key={q.number}>
          <Field.Static label={t('Четверть')}>{q.name ?? q.title}</Field.Static>
          <Field kind="date" name={`f${q.number}`} label={t('С')} value={q.starts} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, starts: v } : row)))} />
          <Field kind="date" name={`t${q.number}`} label={t('По')} value={q.ends} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, ends: v } : row)))} />
        </Field.Row>
      ))}
      <span className="t-caps">{t('Каникулы')}</span>
      {breaks.map((b, i) => (
        <Field.Row key={i}>
          <Field kind="text" name={`bt${i}`} label={t('Название')} value={b.title} onChange={(v) => setBreaks((old) => old.map((row, j) => (j === i ? { ...row, title: v } : row)))} />
          <Field kind="date" name={`bs${i}`} label={t('С')} value={b.starts} onChange={(v) => setBreaks((old) => old.map((row, j) => (j === i ? { ...row, starts: v } : row)))} />
          <Field kind="date" name={`be${i}`} label={t('По')} value={b.ends} onChange={(v) => setBreaks((old) => old.map((row, j) => (j === i ? { ...row, ends: v } : row)))} />
        </Field.Row>
      ))}
      <div className="acad__actions">
        <Button variant="outline" size="sm" onClick={() => setBreaks((old) => [...old, { id: 0, title: t('Каникулы'), starts: rows[0]?.ends ?? '', ends: rows[1]?.starts ?? '' }])}>
          {t('Добавить каникулы')}
        </Button>
      </div>
      {error && <Chip tone="bad">{error}</Chip>}
      <div className="acad__actions">
        <Button onClick={submit} disabled={save.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

const DEFAULT_ROWS = [
  { number: 1, starts: '08:30', ends: '09:15' },
  { number: 2, starts: '09:25', ends: '10:10' },
  { number: 3, starts: '10:25', ends: '11:10' },
  { number: 4, starts: '11:25', ends: '12:10' },
  { number: 5, starts: '12:20', ends: '13:05' },
  { number: 6, starts: '13:15', ends: '14:00' },
  { number: 7, starts: '14:10', ends: '14:55' },
  { number: 8, starts: '15:05', ends: '15:50' },
]

/** Одно расписание звонков: название, звонки и группы, которым оно назначено. */
function BellsDialog({ schedule, onClose }: { schedule?: BellSchedule; onClose: () => void }) {
  const save = useSaveYear()
  const groups = useStudyGroups()
  const [title, setTitle] = useState(schedule?.title ?? '')
  const [rows, setRows] = useState(
    (schedule?.bells.length ? schedule.bells : DEFAULT_ROWS).map((b) => ({ ...b, starts: b.starts.slice(0, 5), ends: b.ends.slice(0, 5) })),
  )
  const [picked, setPicked] = useState<Set<string>>(new Set(schedule?.groups ?? []))
  const [error, setError] = useState('')
  const codes = (groups.data?.results ?? []).map((g) => g.code)
  const submit = () => {
    if (!title.trim()) {
      setError(t('Нужно название'))
      return
    }
    save.mutate(
      { bell_schedules: [{ id: schedule?.id, title: title.trim(), bells: rows, groups: [...picked] }] },
      {
        onSuccess: () => {
          toast.success(t('Звонки сохранены'))
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  return (
    <Modal title={schedule ? schedule.title : t('Новое расписание звонков')} onClose={onClose} wide>
      <Field kind="text" name="title" label={t('Название')} value={title} onChange={setTitle} placeholder={t('Например: вторая смена')} autoFocus />
      {rows.map((b, i) => (
        <Field.Row key={b.number}>
          <Field.Static label={t('Урок')}>{String(b.number)}</Field.Static>
          <Field kind="text" name={`s${b.number}`} label={t('Начало')} value={b.starts} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, starts: v } : row)))} placeholder="08:30" />
          <Field kind="text" name={`e${b.number}`} label={t('Конец')} value={b.ends} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, ends: v } : row)))} placeholder="09:15" />
        </Field.Row>
      ))}
      <span className="t-caps">{t('Группы')}</span>
      <div className="acad__checklist">
        {codes.map((code) => (
          <Field
            key={code}
            kind="checkbox"
            name={`g${code}`}
            label={code}
            checked={picked.has(code)}
            onChange={(on) => {
              const next = new Set(picked)
              if (on) next.add(code)
              else next.delete(code)
              setPicked(next)
            }}
          />
        ))}
      </div>
      {error && <Chip tone="bad">{error}</Chip>}
      <div className="acad__actions">
        <Button onClick={submit} disabled={save.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function ScaleDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [scale, setScale] = useState({ ...year.scale })
  const [error, setError] = useState('')
  const set = (key: keyof typeof scale) => (v: string) => setScale((old) => ({ ...old, [key]: Number(v) }))
  const example = ((8 / 10) * 100 * scale.weight_fo + (12 / 15) * 100 * scale.weight_sor + (20 / 25) * 100 * scale.weight_soch) / Math.max(1, scale.weight_fo + scale.weight_sor + scale.weight_soch)
  const grade = example >= scale.threshold_5 ? 5 : example >= scale.threshold_4 ? 4 : example >= scale.threshold_3 ? 3 : 2
  return (
    <Modal title={t('Шкала оценивания')} onClose={onClose} wide>
      <Field.Row>
        <Field kind="number" name="fo" label={t('ФО, %')} value={scale.weight_fo} onChange={set('weight_fo')} />
        <Field kind="number" name="sor" label={t('СОР, %')} value={scale.weight_sor} onChange={set('weight_sor')} />
        <Field kind="number" name="soch" label={t('СОЧ, %')} value={scale.weight_soch} onChange={set('weight_soch')} />
      </Field.Row>
      <Field.Row>
        <Field kind="number" name="t5" label={t('Пятёрка от, %')} value={scale.threshold_5} onChange={set('threshold_5')} />
        <Field kind="number" name="t4" label={t('Четвёрка от, %')} value={scale.threshold_4} onChange={set('threshold_4')} />
        <Field kind="number" name="t3" label={t('Тройка от, %')} value={scale.threshold_3} onChange={set('threshold_3')} />
      </Field.Row>
      <Field.Row>
        <Field kind="number" name="fomax" label={t('Максимум ФО')} value={scale.fo_max} onChange={set('fo_max')} />
        <Field kind="number" name="edit" label={t('Учитель правит оценку, дней')} value={scale.edit_days} onChange={set('edit_days')} />
      </Field.Row>
      <Rows>
        <Row title={t('Пример: ФО 8, СОР 12 из 15, СОЧ 20 из 25')} value={`${example.toFixed(1)} % → ${grade}`} />
      </Rows>
      {error && <Chip tone="bad">{error}</Chip>}
      <div className="acad__actions">
        <Button
          onClick={() =>
            save.mutate(
              { scale },
              {
                onSuccess: () => {
                  toast.success(t('Шкала сохранена, итоги пересчитаны'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={save.isPending}
        >
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

const SECTIONS: { key: keyof YearScreen['reports']['sections']; label: string }[] = [
  { key: 'attendance', label: tk('Посещаемость по урокам') },
  { key: 'grades', label: tk('Оценки по предметам') },
  { key: 'exams', label: tk('Экзамены и вузы') },
  { key: 'documents', label: tk('Документы для поступления') },
  { key: 'curator', label: tk('Слово куратора') },
  { key: 'discipline', label: tk('Замечания по дисциплине') },
]

function ReportsDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [cadence, setCadence] = useState(year.reports.cadence)
  const [sections, setSections] = useState({ ...year.reports.sections })
  return (
    <Modal title={t('Отчёты родителям')} onClose={onClose}>
      <Field kind="select" name="cadence" label={t('Когда собираются')} value={cadence} onChange={setCadence} options={year.reports.cadences.map((c) => ({ value: c.code, title: t(c.title) }))} />
      <span className="t-caps">{t('Что входит')}</span>
      {SECTIONS.map((s) => (
        <Field key={s.key} kind="checkbox" name={s.key} label={t(s.label)} checked={sections[s.key]} onChange={(on) => setSections((old) => ({ ...old, [s.key]: on }))} />
      ))}
      <div className="acad__actions">
        <Button
          onClick={() =>
            save.mutate(
              { reports: { cadence, sections } },
              {
                onSuccess: () => {
                  toast.success(t('Настройки отчётов сохранены'))
                  onClose()
                },
                onError: (e) => toast.error(e.message),
              },
            )
          }
          disabled={save.isPending}
        >
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Названия предметов на казахском и английском: пусто — показывается русское. */
function SubjectsKkDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [titles, setTitles] = useState<Record<string, string>>(Object.fromEntries(year.subjects.map((s) => [s.code, s.title_kk ?? ''])))
  const [english, setEnglish] = useState<Record<string, string>>(Object.fromEntries(year.subjects.map((s) => [s.code, s.title_en ?? ''])))
  return (
    <Modal title={t('Названия предметов на казахском и английском')} note={t('Интерфейс на этих языках и отчёты родителям на казахском; пусто — русское название')} onClose={onClose} wide>
      <div className="acad__form">
        {year.subjects.map((s) => (
          <div key={s.code} className="acad__pair">
            <Field kind="text" name={`kk-${s.code}`} label={t('{subject} — на казахском', { subject: s.title_ru ?? s.title })} value={titles[s.code] ?? ''} placeholder={s.title_ru ?? s.title} onChange={(value) => setTitles((old) => ({ ...old, [s.code]: value }))} />
            <Field kind="text" name={`en-${s.code}`} label={t('{subject} — на английском', { subject: s.title_ru ?? s.title })} value={english[s.code] ?? ''} placeholder={s.title_ru ?? s.title} onChange={(value) => setEnglish((old) => ({ ...old, [s.code]: value }))} />
          </div>
        ))}
      </div>
      <div className="acad__actions">
        <Button
          disabled={save.isPending}
          onClick={() =>
            save.mutate(
              { subjects: year.subjects.map((s) => ({ code: s.code, title_kk: titles[s.code] ?? '', title_en: english[s.code] ?? '' })) },
              {
                onSuccess: () => {
                  toast.success(t('Названия сохранены'))
                  onClose()
                },
                onError: (e) => toast.error(e.message),
              },
            )
          }
        >
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/**
 * Предметы: ведётся в LMS или только расписание (решение владельца, 07.10.2026).
 * Основной журнал школа ведёт в Kundelik; у «только расписание» урок стоит
 * в неделе, а журнала, оценок и ДЗ нет. Таблица во всю ширину страницы.
 */
function SubjectsCard({ rows, sat }: { rows: SubjectRow[]; sat?: YearScreen['sat'] }) {
  const toggle = useSubjectInLms()
  const kept = rows.filter((row) => row.in_lms).length
  const columns: Column<SubjectRow>[] = [
    {
      key: 'title',
      title: t('Предмет'),
      width: 'auto',
      phone: 'head',
      sortBy: (row) => row.title,
      cell: (row) => (
        <>
          <b>{row.title}</b>
          {row.in_lms && <span className="t-note"> · {row.scheme_title}</span>}
        </>
      ),
    },
    { key: 'weekly', title: t('Уроков в неделю'), width: '16%', align: 'right', sortBy: (row) => row.weekly, cell: (row) => <span className="num">{row.weekly}</span> },
    { key: 'teachers', title: t('Учителей'), width: '12%', align: 'right', sortBy: (row) => row.teachers, cell: (row) => <span className="num">{row.teachers}</span> },
    {
      key: 'is_career',
      title: t('Профтест'),
      hint: t('Учителю этого предмета открыты тесты профориентации'),
      width: '18%',
      sortBy: (row) => (row.is_career ? 0 : 1),
      cell: (row) =>
        row.in_lms ? (
          <SelectField
            className="subjects__lms"
            aria-label={t('{subject}: предмет профориентации или нет', { subject: row.title })}
            value={row.is_career ? 'yes' : 'no'}
            disabled={toggle.isPending}
            onChange={(event) => toggle.mutate({ id: row.id, is_career: event.target.value === 'yes' }, { onError: (e) => toast.error(e.message) })}
          >
            <option value="yes">{t('ведёт тесты')}</option>
            <option value="no">{t('нет')}</option>
          </SelectField>
        ) : (
          <span className="t-note">{t('нет')}</span>
        ),
    },
    {
      key: 'in_lms',
      title: t('В LMS'),
      width: '22%',
      sortBy: (row) => (row.in_lms ? 0 : 1),
      cell: (row) => (
        <SelectField
          className="subjects__lms"
          aria-label={t('{subject}: ведётся в LMS или только расписание', { subject: row.title })}
          value={row.in_lms ? 'yes' : 'no'}
          disabled={toggle.isPending}
          onChange={(event) => toggle.mutate({ id: row.id, in_lms: event.target.value === 'yes' }, { onError: (e) => toast.error(e.message) })}
        >
          <option value="yes">{t('ведётся в LMS')}</option>
          <option value="no">{t('только расписание')}</option>
        </SelectField>
      ),
    },
  ]
  return (
    <DataCard title={t('Предметы')} count={rows.length || undefined} right={<span className="t-note">{t('ведутся в LMS: {kept} из {total}', { kept, total: rows.length })}</span>} empty={rows.length === 0 && t('предметов нет — их заводит импорт расписания')}>
      {/* SAT: один предмет или два — правило школы; журналы разносит команда, не переключатель (11.10.2026) */}
      {sat && (
        <p className="t-note subjects__sat">
          {sat.two ? t('SAT — два предмета: SAT Math и SAT Verbal') : t('SAT — один предмет, Math и Verbal — разделы отчёта у журналов')}
          {sat.pending && (
            <Chip tone="warn" size="sm">
              {sat.two ? t('журналы ещё не разнесены — команда sat_subjects --split') : t('журналы ещё не сведены — команда sat_subjects --merge')}
            </Chip>
          )}
        </p>
      )}
      {rows.length > 0 && <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} fit />}
    </DataCard>
  )
}

function NewYearDialog({ onClose }: { onClose: () => void }) {
  const save = useSaveYear()
  const [title, setTitle] = useState('')
  const [starts, setStarts] = useState('')
  const [ends, setEnds] = useState('')
  const [error, setError] = useState('')
  return (
    <Modal title={t('Учебный год')} onClose={onClose}>
      <Field kind="text" name="title" label={t('Название')} value={title} onChange={setTitle} placeholder="2026–2027" />
      <Field.Row>
        <Field kind="date" name="starts" label={t('Начало')} value={starts} onChange={setStarts} />
        <Field kind="date" name="ends" label={t('Конец')} value={ends} onChange={setEnds} error={error || undefined} />
      </Field.Row>
      <div className="acad__actions">
        <Button
          onClick={() =>
            save.mutate(
              { year: { title, starts, ends }, quarters: [{ number: 1, title: t('1 четверть'), starts, ends }] },
              {
                onSuccess: () => {
                  toast.success(t('Учебный год заведён'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={save.isPending}
        >
          {t('Завести')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/** Карточка расписания звонков: название, группы, звонки строками. */
function BellsCard({ schedule, onEdit, onDrop }: { schedule: BellSchedule; onEdit: () => void; onDrop?: () => void }) {
  return (
    <DataCard
      title={schedule.name ?? schedule.title}
      note={schedule.groups.length ? schedule.groups.join(', ') : t('группы не назначены')}
      right={
        <RowMenu>
          <RowMenuItem onClick={onEdit}>{t('Изменить')}</RowMenuItem>
          {onDrop && (
            <RowMenuItem risk onClick={onDrop}>
              {t('Удалить расписание звонков')}
            </RowMenuItem>
          )}
        </RowMenu>
      }
    >
      <div className="year__slots">
        {schedule.bells.map((b) => (
          <div key={b.number} className="year__slot">
            <span className="num year__slotn">{b.number}</span>
            <span className="num">{`${b.starts.slice(0, 5)}–${b.ends.slice(0, 5)}`}</span>
          </div>
        ))}
      </div>
    </DataCard>
  )
}

export default function AcademicYear() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useYear()
  const close = useCloseQuarter()
  const save = useSaveYear()
  const [dialog, setDialog] = useState<'quarters' | 'scale' | 'reports' | 'subjects' | 'year' | { bells: BellSchedule | null } | null>(null)
  const [closing, setClosing] = useState<YearScreen['quarters'][number] | null>(null)
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (!data.year)
    return (
      <div>
        <ScreenHead title={t('Учебный год')} actions={<Button size="sm" onClick={() => setDialog('year')}>{t('Завести учебный год')}</Button>} />
        <DataCard title={t('Учебного года нет')} empty={t('год ещё не заведён')} emptyAction={<Button variant="secondary" size="sm" onClick={() => setDialog('year')}>{t('Завести')}</Button>} />
        {dialog === 'year' && <NewYearDialog onClose={() => setDialog(null)} />}
      </div>
    )
  const current = data.quarters.find((q) => q.current) ?? data.quarters.find((q) => !q.past) ?? data.quarters[data.quarters.length - 1]
  const schedules = data.bell_schedules ?? []
  const first = data.quarters[0]
  const last = data.quarters[data.quarters.length - 1]
  // каникулы — подписью под своей четвертью: те, что начинаются после её конца и до следующей
  const breakAfter = (index: number) => {
    const quarter = data.quarters[index]
    const next = data.quarters[index + 1]
    return data.breaks.find((b) => b.starts > quarter.ends && (!next || b.starts < next.starts))
  }
  const days = (from: string, to: string) => Math.max(1, (Date.parse(to) - Date.parse(from)) / 86_400_000)
  const today = todayAlmaty()
  const filled = (q: YearScreen['quarters'][number]) =>
    q.past || q.closed ? 100 : q.current ? Math.round((Math.min(days(q.starts, today), days(q.starts, q.ends)) / days(q.starts, q.ends)) * 100) : 0
  const named = (total: number, n: number) => (total ? Math.round((n / total) * 100) : 0)
  const kk = data.subjects.filter((x) => x.title_kk).length
  const en = data.subjects.filter((x) => x.title_en).length
  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Учебный год {title}', { title: data.year.title })}
        subtitle={
          first && last
            ? `${dateWords(first.starts)} – ${dateWords(last.ends)}${current?.current ? ` · ${t('идёт {quarter}', { quarter: (current.name ?? current.title).toLowerCase() })}` : ''}`
            : undefined
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/school-settings')}>
              {t('Настройки школы')}
            </Button>
            <Button size="sm" onClick={() => setDialog({ bells: null })}>
              {t('Добавить расписание звонков')}
            </Button>
          </>
        }
      />
      <div className="lay-3">
        <DataCard className="card--beam lay-span2" title={t('Четверти и каникулы')} right={<Button variant="link" size="sm" onClick={() => setDialog('quarters')}>{t('Изменить')}</Button>}>
          <div className="year__track" aria-hidden="true">
            {data.quarters.map((q) => (
              <div key={q.id} className="bar bar--accent" style={{ flex: days(q.starts, q.ends) }}>
                <i style={{ width: `${filled(q)}%`, background: 'var(--accent-grad)' }} />
              </div>
            ))}
          </div>
          <div className="year__quarters">
            {data.quarters.map((q, index) => {
              const rest = breakAfter(index)
              return (
                <div key={q.id} className={`year__quarter${q.current ? ' year__quarter--now' : ''}`}>
                  <span className="year__qhead">
                    <b>{q.name ?? q.title}</b>
                    {q.closed ? <Chip tone="good" size="sm">{t('итоги закрыты')}</Chip> : q.current ? <Chip tone="accent" size="sm">{t('идёт')}</Chip> : q.past ? <Chip size="sm">{t('прошла')}</Chip> : null}
                  </span>
                  <span className="num t-note year__dates">{`${dateShort(q.starts)} – ${dateShort(q.ends)}`}</span>
                  {rest && <span className="t-note year__rest">{`${rest.name ?? rest.title}: ${dateWords(rest.starts)} — ${dateWords(rest.ends)}`}</span>}
                </div>
              )
            })}
          </div>
          {(data.holidays.length > 0 || data.breaks.some((b) => !data.quarters.some((_, i) => breakAfter(i) === b))) && (
            <div className="year__holidays">
              {data.breaks
                .filter((b) => !data.quarters.some((_, i) => breakAfter(i) === b))
                .map((b) => (
                  <Chip key={`b${b.id}`} size="sm">{`${b.name ?? b.title} · ${dateWords(b.starts)} — ${dateWords(b.ends)}`}</Chip>
                ))}
              {data.holidays.map((h) => (
                <Chip key={`h${h.id}`} size="sm">{`${h.name ?? h.title} · ${dateWords(h.date)}`}</Chip>
              ))}
            </div>
          )}
        </DataCard>
        {current && (
          <DataCard title={t('Итоги четверти')} right={current.closed ? <Chip tone="good" size="sm">{t('итоги закрыты')}</Chip> : <Chip tone="accent" size="sm">{current.name ?? current.title}</Chip>}>
            <span className="year__big num">{dateWords(current.ends)}</span>
            <span className="t-note">{t('Итоги в журнале до этой даты')}</span>
            <div className="acad__actions year__push">
              <Button variant={current.closed ? 'outline' : 'default'} size="sm" onClick={() => (current.closed ? close.mutate({ id: current.id, closed: false }, { onSuccess: () => toast.success(t('Приём итогов открыт')) }) : setClosing(current))}>
                {current.closed ? t('Открыть приём итогов') : t('Закрыть приём итогов')}
              </Button>
            </div>
          </DataCard>
        )}
      </div>
      <div className="lay-3">
        <DataCard title={t('Шкала оценивания')} right={<Button variant="link" size="sm" onClick={() => setDialog('scale')}>{t('Изменить')}</Button>}>
          <div className="shares" aria-hidden="true">
            <i style={{ flex: data.scale.weight_fo, background: 'var(--glint)' }} />
            <i style={{ flex: data.scale.weight_sor, background: 'var(--accent-2)' }} />
            <i style={{ flex: data.scale.weight_soch, background: 'var(--accent)' }} />
          </div>
          <div className="year__weights">
            <span><b className="num">{`${data.scale.weight_fo} %`}</b><span className="t-note">{t('ФО · 1–{max}', { max: data.scale.fo_max })}</span></span>
            <span><b className="num">{`${data.scale.weight_sor} %`}</b><span className="t-note">{t('СОР')}</span></span>
            <span><b className="num">{`${data.scale.weight_soch} %`}</b><span className="t-note">{t('СОЧ')}</span></span>
          </div>
          <Rows>
            <Row title={t('Перевод в оценку')} note={t('5: от {five} % · 4: от {four} % · 3: от {three} %', {
                five: data.scale.threshold_5,
                four: data.scale.threshold_4,
                three: data.scale.threshold_3,
              })} />
            <Row title={t('Правка оценок учителем')} value={tn(data.scale.edit_days, '{n} день|{n} дня|{n} дней')} />
          </Rows>
        </DataCard>
        <DataCard title={t('Отчёты родителям')} right={<Button variant="link" size="sm" onClick={() => setDialog('reports')}>{t('Изменить')}</Button>}>
          <span className="year__lead">{data.reports.cadence_title}</span>
          <div className="year__holidays">
            {SECTIONS.filter((x) => data.reports.sections[x.key]).map((x) => (
              <Chip key={x.key} size="sm">{t(x.label).toLowerCase()}</Chip>
            ))}
          </div>
        </DataCard>
        <DataCard title={t('Названия предметов')} right={<Button variant="link" size="sm" onClick={() => setDialog('subjects')}>{t('Изменить')}</Button>}>
          <div className="year__names">
            <span className="year__nameshead"><span>{t('На казахском')}</span><span className="t-note num">{t('{filled} из {total}', { filled: kk, total: data.subjects.length })}</span></span>
            <Bar percent={named(data.subjects.length, kk)} />
            <span className="year__nameshead"><span>{t('На английском')}</span><span className="t-note num">{t('{filled} из {total}', { filled: en, total: data.subjects.length })}</span></span>
            <Bar percent={named(data.subjects.length, en)} />
          </div>
        </DataCard>
      </div>
      {/* общей сетки нет: группе без звонков негде взять время урока — это ошибка,
          и она названа одной тихой строкой над рядом звонков, без своей карточки */}
      {data.groups_without_bells.length > 0 && (
        <p className="warnline">
          <span className="warnline__what">{t('Не назначены звонки: {groups}', { groups: data.groups_without_bells.join(', ') })}</span>
          <span>{t('У уроков этих групп нет времени начала. Отметьте группы в расписании звонков или добавьте новое.')}</span>
        </p>
      )}
      {schedules.length === 0 ? (
        <DataCard title={t('Звонки')} empty={t('расписаний звонков нет')} emptyAction={<Button variant="secondary" size="sm" onClick={() => setDialog({ bells: null })}>{t('Добавить расписание звонков')}</Button>} />
      ) : (
        <div className="lay-4 year__bells">
          {schedules.map((schedule) => (
            <BellsCard
              key={schedule.id}
              schedule={schedule}
              onEdit={() => setDialog({ bells: schedule })}
              onDrop={() => save.mutate({ drop_bell_schedule: schedule.id }, { onSuccess: () => toast.success(t('Расписание звонков удалено')), onError: (e) => toast.error(e.message) })}
            />
          ))}
        </div>
      )}
      <SubjectsCard rows={data.subject_rows ?? []} sat={data.sat} />
      {dialog === 'quarters' && <QuartersDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'scale' && <ScaleDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'reports' && <ReportsDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'subjects' && <SubjectsKkDialog year={data} onClose={() => setDialog(null)} />}
      {typeof dialog === 'object' && dialog !== null && 'bells' in dialog && <BellsDialog schedule={dialog.bells ?? undefined} onClose={() => setDialog(null)} />}
      <ConfirmDialog
        open={closing !== null}
        title={closing ? t('Закрыть приём итогов · {quarter}?', { quarter: closing.name ?? closing.title }) : ''}
        consequences={[t('Учителя больше не смогут менять оценки и итоговые отметки этой четверти'), t('Отчёты родителям за четверть соберутся сами')]}
        confirmLabel={t('Закрыть')}
        busy={close.isPending}
        onConfirm={() =>
          closing &&
          close.mutate(
            { id: closing.id, closed: true },
            {
              onSuccess: () => {
                toast.success(t('Приём итогов закрыт'))
                setClosing(null)
              },
              onError: (e) => toast.error(e.message),
            },
          )
        }
        onCancel={() => setClosing(null)}
      />
    </div>
  )
}
