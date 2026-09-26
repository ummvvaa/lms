/**
 * Учебный год: четверти и каникулы, звонки, шкала оценивания, настройки
 * отчётов родителям (только когда собирать и какие разделы), закрытие четверти.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCloseQuarter, useSaveYear, useYear, type YearScreen } from '../../api/academics'
import ConfirmDialog from '../../components/ConfirmDialog'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateFull, dateWords, NoteCard } from './shared'

function QuartersDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [rows, setRows] = useState(year.quarters.map((q) => ({ ...q })))
  const [breaks, setBreaks] = useState(year.breaks.map((b) => ({ ...b })))
  const [error, setError] = useState('')
  const submit = () =>
    save.mutate(
      { quarters: rows.map((q) => ({ number: q.number, title: q.title, starts: q.starts, ends: q.ends })), breaks: breaks.map((b) => ({ title: b.title, starts: b.starts, ends: b.ends })) },
      { onSuccess: () => { toast.success(t('Четверти сохранены')); onClose() }, onError: (e) => setError(e.message) },
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
      {error && <Chip tone="bad" className="badge--line">{error}</Chip>}
      <div className="acad__actions">
        <Button onClick={submit} disabled={save.isPending}>{t('Сохранить')}</Button>
        <Button variant="outline" onClick={onClose}>{t('Отмена')}</Button>
      </div>
    </Modal>
  )
}

function BellsDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [rows, setRows] = useState(year.bells.map((b) => ({ ...b, starts: b.starts.slice(0, 5), ends: b.ends.slice(0, 5) })))
  const [error, setError] = useState('')
  return (
    <Modal title={t('Звонки')} onClose={onClose} wide>
      {rows.map((b, i) => (
        <Field.Row key={b.number}>
          <Field.Static label={t('Урок')}>{String(b.number)}</Field.Static>
          <Field kind="text" name={`s${b.number}`} label={t('Начало')} value={b.starts} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, starts: v } : row)))} placeholder="08:30" />
          <Field kind="text" name={`e${b.number}`} label={t('Конец')} value={b.ends} onChange={(v) => setRows((old) => old.map((row, j) => (j === i ? { ...row, ends: v } : row)))} placeholder="09:15" />
        </Field.Row>
      ))}
      {error && <Chip tone="bad" className="badge--line">{error}</Chip>}
      <div className="acad__actions">
        <Button onClick={() => save.mutate({ bells: rows }, { onSuccess: () => { toast.success(t('Звонки сохранены')); onClose() }, onError: (e) => setError(e.message) })} disabled={save.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>{t('Отмена')}</Button>
      </div>
    </Modal>
  )
}

function ScaleDialog({ year, onClose }: { year: YearScreen; onClose: () => void }) {
  const save = useSaveYear()
  const [scale, setScale] = useState({ ...year.scale })
  const [error, setError] = useState('')
  const set = (key: keyof typeof scale) => (v: string) => setScale((old) => ({ ...old, [key]: Number(v) }))
  const example = (8 / 10 * 100 * scale.weight_fo + (12 / 15) * 100 * scale.weight_sor + (20 / 25) * 100 * scale.weight_soch) / Math.max(1, scale.weight_fo + scale.weight_sor + scale.weight_soch)
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
      <p className="acad__note">
        {t('Пример при этих весах: средний ФО 8, СОР 12 из 15, СОЧ 20 из 25 →')} {example.toFixed(1)} % → {grade}. {t('Сумма весов должна быть 100.')}
      </p>
      {error && <Chip tone="bad" className="badge--line">{error}</Chip>}
      <div className="acad__actions">
        <Button onClick={() => save.mutate({ scale }, { onSuccess: () => { toast.success(t('Шкала сохранена, итоги пересчитаны')); onClose() }, onError: (e) => setError(e.message) })} disabled={save.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>{t('Отмена')}</Button>
      </div>
    </Modal>
  )
}

const SECTIONS: { key: keyof YearScreen['reports']['sections']; label: string }[] = [
  { key: 'attendance', label: 'Посещаемость по урокам' },
  { key: 'grades', label: 'Оценки по предметам' },
  { key: 'exams', label: 'Экзамены и вузы' },
  { key: 'documents', label: 'Документы для поступления' },
  { key: 'curator', label: 'Слово куратора' },
  { key: 'discipline', label: 'Замечания по дисциплине' },
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
      <p className="acad__note">{t('Проверка куратором обязательна всегда; писем родителям нет — куратор отправляет PDF сам.')}</p>
      <div className="acad__actions">
        <Button onClick={() => save.mutate({ reports: { cadence, sections } }, { onSuccess: () => { toast.success(t('Настройки отчётов сохранены')); onClose() }, onError: (e) => toast.error(e.message) })} disabled={save.isPending}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>{t('Отмена')}</Button>
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
    <Modal title={t('Учебный год')} note={t('Год, четверти и звонки заводит академический директор')} onClose={onClose}>
      <Field kind="text" name="title" label={t('Название')} value={title} onChange={setTitle} placeholder="2026–2027" />
      <Field.Row>
        <Field kind="date" name="starts" label={t('Начало')} value={starts} onChange={setStarts} />
        <Field kind="date" name="ends" label={t('Конец')} value={ends} onChange={setEnds} error={error || undefined} />
      </Field.Row>
      <div className="acad__actions">
        <Button onClick={() => save.mutate({ year: { title, starts, ends }, quarters: [{ number: 1, title: t('1 четверть'), starts, ends }] }, { onSuccess: () => { toast.success(t('Учебный год заведён')); onClose() }, onError: (e) => setError(e.message) })} disabled={save.isPending}>
          {t('Завести')}
        </Button>
        <Button variant="outline" onClick={onClose}>{t('Отмена')}</Button>
      </div>
    </Modal>
  )
}

export default function AcademicYear() {
  const { data, isLoading, error } = useYear()
  const close = useCloseQuarter()
  const [dialog, setDialog] = useState<'quarters' | 'bells' | 'scale' | 'reports' | 'year' | null>(null)
  const [closing, setClosing] = useState<YearScreen['quarters'][number] | null>(null)
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (!data.year)
    return (
      <div>
        <ScreenHead title={t('Учебный год')} actions={<Button size="sm" onClick={() => setDialog('year')}>{t('Завести учебный год')}</Button>} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Учебного года нет')} empty={t('заведите год: четверти, звонки и шкала появятся с умолчаниями')} emptyAction={<Button variant="secondary" size="sm" onClick={() => setDialog('year')}>{t('Завести')}</Button>} />
          </div>
          <div className="acad__stack">
            <NoteCard title={t('Что здесь будет')}>{t('Четверти, каникулы, праздники, звонки, шкала оценивания и настройки отчётов родителям.')}</NoteCard>
          </div>
        </div>
        {dialog === 'year' && <NewYearDialog onClose={() => setDialog(null)} />}
      </div>
    )
  const current = data.quarters.find((q) => q.current) ?? data.quarters.find((q) => !q.past) ?? data.quarters[data.quarters.length - 1]
  return (
    <div>
      <ScreenHead title={`${t('Учебный год')} ${data.year.title}`} subtitle={t('Четверти, звонки, шкала оценивания и отчёты родителям. Меняют Кымбат и администратор.')} />
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
          <DataCard title={t('Звонки')} right={<Button variant="link" size="sm" onClick={() => setDialog('bells')}>{t('Изменить')}</Button>}>
            <Rows>
              {data.bells.map((b) => (
                <Row key={b.number} lead={<b className="num">{b.number}</b>} title={`${b.starts.slice(0, 5)}–${b.ends.slice(0, 5)}`} />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Шкала оценивания')} right={<Button variant="link" size="sm" onClick={() => setDialog('scale')}>{t('Изменить')}</Button>}>
            <Rows>
              <Row title={t('ФО')} note={`${t('формативное, от 1 до')} ${data.scale.fo_max}`} value={`${data.scale.weight_fo} %`} />
              <Row title={t('СОР')} note={t('за раздел, баллы из максимума')} value={`${data.scale.weight_sor} %`} />
              <Row title={t('СОЧ')} note={t('за четверть, баллы из максимума')} value={`${data.scale.weight_soch} %`} />
              <Row title={t('Перевод в оценку')} note={`5: ${t('от')} ${data.scale.threshold_5} % · 4: ${t('от')} ${data.scale.threshold_4} % · 3: ${t('от')} ${data.scale.threshold_3} %`} />
              <Row title={t('Правка оценок учителем')} note={`${data.scale.edit_days} ${t('дней, дальше — через Кымбат')}`} />
            </Rows>
          </DataCard>
          <DataCard title={t('Отчёты родителям')} right={<Button variant="link" size="sm" onClick={() => setDialog('reports')}>{t('Изменить')}</Button>}>
            <Rows>
              <Row title={t('Когда собираются')} note={data.reports.cadence_title} />
              <Row title={t('Что входит')} note={SECTIONS.filter((s) => data.reports.sections[s.key]).map((s) => t(s.label).toLowerCase()).join(', ')} />
              <Row title={t('Перед выгрузкой')} note={t('куратор проверяет всегда; писем нет — PDF уходит родителям через куратора')} />
            </Rows>
          </DataCard>
          {current && (
            <DataCard title={t('Итоги четверти')}>
              <p className="acad__note">
                {t('Учителя выставляют итог в журнале до')} {dateWords(current.ends)}. {t('После закрытия итоги правит только Кымбат или администратор, отчёты за четверть собираются сами.')}
              </p>
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
      {dialog === 'bells' && <BellsDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'scale' && <ScaleDialog year={data} onClose={() => setDialog(null)} />}
      {dialog === 'reports' && <ReportsDialog year={data} onClose={() => setDialog(null)} />}
      <ConfirmDialog
        open={closing !== null}
        title={closing ? `${t('Закрыть приём итогов')} · ${closing.title}?` : ''}
        consequences={[t('Учителя больше не смогут менять оценки и итоговые отметки этой четверти'), t('Отчёты родителям за четверть соберутся сами')]}
        confirmLabel={t('Закрыть')}
        busy={close.isPending}
        onConfirm={() => closing && close.mutate({ id: closing.id, closed: true }, { onSuccess: () => { toast.success(t('Приём итогов закрыт')); setClosing(null) }, onError: (e) => toast.error(e.message) })}
        onCancel={() => setClosing(null)}
      />
    </div>
  )
}
