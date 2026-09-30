/**
 * Учебный год: четверти и каникулы, расписания звонков карточками
 * (общее и назначенные группам — решение владельца, 27.09.2026), шкала
 * оценивания, настройки отчётов родителям, закрытие четверти.
 * Казахские названия предметов — для отчётов родителям на казахском (30.09.2026).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCloseQuarter, useSaveYear, useYear, type BellSchedule, type YearScreen } from '../../api/academics'
import { useStudyGroups } from '../../api/hooks'
import ConfirmDialog from '../../components/ConfirmDialog'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { dateFull, dateWords } from './shared'

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
          <Field.Static label={t('Четверть')}>{q.title}</Field.Static>
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
    if (!schedule?.is_default && !title.trim()) {
      setError(t('Нужно название'))
      return
    }
    save.mutate(
      { bell_schedules: [{ id: schedule?.id, title: schedule?.is_default ? undefined : title.trim(), bells: rows, groups: schedule?.is_default ? undefined : [...picked] }] },
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
      {!schedule?.is_default && <Field kind="text" name="title" label={t('Название')} value={title} onChange={setTitle} placeholder={t('Например: вторая смена')} autoFocus />}
      {rows.map((b, i) => (
        <Field.Row key={b.number}>
          <Field.Static label={t('Урок')}>{String(b.number)}</Field.Static>
          <Field kind="text" name={`s${b.number}`} label={t('Начало')} value={b.starts} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, starts: v } : row)))} placeholder="08:30" />
          <Field kind="text" name={`e${b.number}`} label={t('Конец')} value={b.ends} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, ends: v } : row)))} placeholder="09:15" />
        </Field.Row>
      ))}
      {!schedule?.is_default && (
        <>
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
        </>
      )}
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
      title={schedule.title}
      note={schedule.is_default ? t('все группы без своего расписания') : schedule.groups.length ? schedule.groups.join(', ') : t('группы не назначены')}
      right={
        <span className="acad__inline">
          <Button variant="link" size="sm" onClick={onEdit}>
            {t('Изменить')}
          </Button>
          {onDrop && (
            <RowMenu>
              <RowMenuItem risk onClick={onDrop}>
                {t('Удалить расписание звонков')}
              </RowMenuItem>
            </RowMenu>
          )}
        </span>
      }
    >
      <Rows>
        {schedule.bells.map((b) => (
          <Row key={b.number} lead={<b className="num">{b.number}</b>} title={`${b.starts.slice(0, 5)}–${b.ends.slice(0, 5)}`} />
        ))}
      </Rows>
    </DataCard>
  )
}

export default function AcademicYear() {
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
  return (
    <div>
      <ScreenHead
        title={t('Учебный год {title}', { title: data.year.title })}
        actions={
          <Button size="sm" onClick={() => setDialog({ bells: null })}>
            {t('Добавить расписание звонков')}
          </Button>
        }
      />
      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Четверти')} right={<Button variant="link" size="sm" onClick={() => setDialog('quarters')}>{t('Изменить')}</Button>}>
            <Rows>
              {data.quarters.map((q) => (
                <Row
                  key={q.id}
                  lead={<b className="num">{q.number}</b>}
                  title={q.title}
                  note={`${dateFull(q.starts)} — ${dateFull(q.ends)}`}
                  right={q.closed ? <Chip tone="good">{t('итоги закрыты')}</Chip> : q.current ? <Chip tone="accent">{t('идёт')}</Chip> : q.past ? <Chip tone="neutral">{t('прошла')}</Chip> : undefined}
                />
              ))}
              {data.breaks.map((b) => (
                <Row key={b.id} icon="calendar" title={b.title} note={`${dateWords(b.starts)} — ${dateWords(b.ends)}`} />
              ))}
              {data.holidays.map((h) => (
                <Row key={h.id} icon="star" title={h.title} note={dateWords(h.date)} />
              ))}
            </Rows>
          </DataCard>
          {schedules.map((schedule) => (
            <BellsCard
              key={schedule.id}
              schedule={schedule}
              onEdit={() => setDialog({ bells: schedule })}
              onDrop={
                schedule.is_default
                  ? undefined
                  : () => save.mutate({ drop_bell_schedule: schedule.id }, { onSuccess: () => toast.success(t('Расписание звонков удалено')), onError: (e) => toast.error(e.message) })
              }
            />
          ))}
        </div>
        <div className="acad__stack">
          <DataCard title={t('Шкала оценивания')} right={<Button variant="link" size="sm" onClick={() => setDialog('scale')}>{t('Изменить')}</Button>}>
            <Rows>
              <Row title={t('ФО')} note={t('от 1 до {max}', { max: data.scale.fo_max })} value={`${data.scale.weight_fo} %`} />
              <Row title={t('СОР')} value={`${data.scale.weight_sor} %`} />
              <Row title={t('СОЧ')} value={`${data.scale.weight_soch} %`} />
              <Row title={t('Перевод в оценку')} note={t('5: от {five} % · 4: от {four} % · 3: от {three} %', {
                  five: data.scale.threshold_5,
                  four: data.scale.threshold_4,
                  three: data.scale.threshold_3,
                })} />
              <Row title={t('Правка оценок учителем')} value={tn(data.scale.edit_days, '{n} день|{n} дня|{n} дней')} />
            </Rows>
          </DataCard>
          <DataCard title={t('Отчёты родителям')} right={<Button variant="link" size="sm" onClick={() => setDialog('reports')}>{t('Изменить')}</Button>}>
            <Rows>
              <Row title={t('Когда собираются')} note={data.reports.cadence_title} />
              <Row title={t('Что входит')} note={SECTIONS.filter((s) => data.reports.sections[s.key]).map((s) => t(s.label).toLowerCase()).join(', ')} />
            </Rows>
          </DataCard>
          <DataCard title={t('Названия предметов на других языках')} right={<Button variant="link" size="sm" onClick={() => setDialog('subjects')}>{t('Изменить')}</Button>}>
            <Rows>
              <Row
                title={t('На казахском')}
                note={t('{filled} из {total} заполнено', { filled: data.subjects.filter((s) => s.title_kk).length, total: data.subjects.length })}
              />
              <Row
                title={t('На английском')}
                note={t('{filled} из {total} заполнено', { filled: data.subjects.filter((s) => s.title_en).length, total: data.subjects.length })}
              />
            </Rows>
          </DataCard>
          {current && (
            <DataCard title={t('Итоги четверти')}>
              <Rows>
                <Row title={t('Итоги в журнале до')} value={dateWords(current.ends)} />
              </Rows>
              <div className="acad__actions">
                <Button variant={current.closed ? 'outline' : 'default'} size="sm" onClick={() => (current.closed ? close.mutate({ id: current.id, closed: false }, { onSuccess: () => toast.success(t('Приём итогов открыт')) }) : setClosing(current))}>
                  {current.closed ? `${t('Открыть приём итогов')} · ${current.title}` : `${t('Закрыть приём итогов')} · ${current.title}`}
                </Button>
              </div>
            </DataCard>
          )}
        </div>
      </div>
      {dialog === 'quarters' && <QuartersDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'scale' && <ScaleDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'reports' && <ReportsDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'subjects' && <SubjectsKkDialog year={data} onClose={() => setDialog(null)} />}
      {typeof dialog === 'object' && dialog !== null && 'bells' in dialog && <BellsDialog schedule={dialog.bells ?? undefined} onClose={() => setDialog(null)} />}
      <ConfirmDialog
        open={closing !== null}
        title={closing ? t('Закрыть приём итогов · {quarter}?', { quarter: closing.title }) : ''}
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
