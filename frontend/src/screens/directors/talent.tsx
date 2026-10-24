/**
 * Общие части кабинета директора талантов (24.10.2026): выбор учеников
 * в окне, новая олимпиада и новое освобождение от уроков.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSaveOlympiad, useSaveRelease, type OlympiadRow, type StudentBrief } from '../../api/directors'
import { useDirectoryEntries, useStudents } from '../../api/hooks'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Segmented } from '../../components/patterns'
import { ErrorNote } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import { t } from '../../i18n'
import { formatDayMonth } from '../../lib/format'

export interface Pickable {
  id: number
  name: string
  note: string
}

/** Список с галочками и поиском по фамилии: участники олимпиады, освобождаемые. */
export function StudentPicks({
  items,
  picked,
  onChange,
  onSearch,
}: {
  items: Pickable[]
  picked: number[]
  onChange: (next: number[]) => void
  /** поиск на сервере (вся школа); без него — по уже загруженному списку */
  onSearch?: (query: string) => void
}) {
  const [query, setQuery] = useState('')
  const shown = onSearch ? items : items.filter((item) => !query || item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  const toggle = (id: number) => onChange(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id])
  return (
    <>
      <Field
        usageFilter
        className="filters__search"
        name="pick-q"
        label={t('Поиск')}
        value={query}
        placeholder={t('Фамилия или имя')}
        onChange={(value) => {
          setQuery(value)
          onSearch?.(value)
        }}
      />
      <div className="dir__picks">
        {shown.length === 0 && <p className="t-note">{t('никого не нашли')}</p>}
        {shown.map((item) => (
          <label key={item.id} className="dir__pick">
            <Checkbox checked={picked.includes(item.id)} onCheckedChange={() => toggle(item.id)} aria-label={item.name} />
            <span>{item.name}</span>
            <span className="t-note">{item.note}</span>
          </label>
        ))}
      </div>
    </>
  )
}

/** Ученики школы для выбора — поиск идёт на сервере, граница видимости та же. */
export function useSchoolPicks(search: string): Pickable[] {
  const students = useStudents({ search, page_size: 50 })
  return (students.data?.results ?? []).map((s) => ({ id: s.id, name: s.full_name, note: s.group_code ?? '' }))
}

export const fromBriefs = (rows: StudentBrief[]): Pickable[] => rows.map((s) => ({ id: s.id, name: s.full_name, note: s.group }))

/** Новая олимпиада: название, предмет из справочника, место, уровень, даты. */
export function OlympiadDialog({ levels, onClose, onSaved }: { levels: { value: string; label: string }[]; onClose: () => void; onSaved?: (row: OlympiadRow) => void }) {
  const save = useSaveOlympiad()
  const subjects = useDirectoryEntries('subjects')
  const [title, setTitle] = useState('')
  const [subject, setSubject] = useState('')
  const [place, setPlace] = useState('')
  const [level, setLevel] = useState(levels[1]?.value ?? 'city')
  const [starts, setStarts] = useState('')
  const [ends, setEnds] = useState('')
  return (
    <Modal title={t('Новая олимпиада')} note={t('видно академ директору и кураторам')} onClose={onClose}>
      <div className="dir__form">
        <Field className="dir__wide" name="title" label={t('Название')} value={title} onChange={setTitle} autoFocus />
        <Field
          kind="select"
          name="subject"
          label={t('Предмет')}
          value={subject}
          onChange={setSubject}
          placeholder={t('Без предмета')}
          options={(subjects.data?.results ?? []).filter((row) => row.is_active).map((row) => ({ value: String(row.id), title: row.name }))}
        />
        <Field name="place" label={t('Место')} value={place} onChange={setPlace} />
        <div className="dir__wide">
          <Segmented value={level} onChange={setLevel} label={t('Уровень')} items={levels.map((row) => ({ value: row.value, label: row.label }))} />
        </div>
        <Field kind="date" name="starts" label={t('Дата с')} value={starts} onChange={setStarts} />
        <Field kind="date" name="ends" label={t('Дата по')} value={ends} onChange={setEnds} hint={t('один день — оставьте пустым')} />
      </div>
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!title.trim() || !starts || save.isPending}
          onClick={() =>
            save.mutate(
              { title, level, starts, ends: ends || starts, place, subject: subject ? Number(subject) : null },
              {
                onSuccess: (row) => {
                  toast.success(t('Олимпиада добавлена · видно академ директору и кураторам'))
                  onSaved?.(row)
                  onClose()
                },
              },
            )
          }
        >
          {t('Сохранить')}
        </Button>
      </div>
    </Modal>
  )
}

/** Освобождение по олимпиаде: ученики, даты, весь день или уроки «с–по». */
export function ReleaseDialog({
  olympiads,
  olympiad: initial,
  onClose,
}: {
  olympiads: OlympiadRow[]
  olympiad?: OlympiadRow
  onClose: () => void
}) {
  const save = useSaveRelease()
  const [olympiadId, setOlympiadId] = useState(String(initial?.id ?? olympiads[0]?.id ?? ''))
  const chosen = olympiads.find((row) => String(row.id) === olympiadId) ?? initial
  const [starts, setStarts] = useState(chosen?.starts ?? '')
  const [ends, setEnds] = useState(chosen?.ends ?? '')
  const [mode, setMode] = useState<'day' | 'slots'>('day')
  const [slotFrom, setSlotFrom] = useState('1')
  const [slotTo, setSlotTo] = useState('4')
  const [picked, setPicked] = useState<number[]>(initial?.entries?.map((e) => e.student.id) ?? [])
  const [search, setSearch] = useState('')
  const school = useSchoolPicks(search)
  const entries = fromBriefs(initial?.entries?.map((e) => e.student) ?? [])
  const items = entries.length ? entries : school
  return (
    <Modal title={t('Новое освобождение')} note={t('видно академ директору и кураторам групп')} onClose={onClose} wide>
      <div className="dir__form">
        <Field
          className="dir__wide"
          kind="select"
          name="olympiad"
          label={t('Олимпиада')}
          value={olympiadId}
          onChange={(value) => {
            setOlympiadId(value)
            const row = olympiads.find((o) => String(o.id) === value)
            if (row) {
              setStarts(row.starts)
              setEnds(row.ends)
            }
          }}
          options={olympiads.map((row) => ({ value: String(row.id), title: `${row.title} · ${formatDayMonth(row.starts)}` }))}
        />
        <Field kind="date" name="starts" label={t('С')} value={starts} onChange={setStarts} />
        <Field kind="date" name="ends" label={t('По')} value={ends} onChange={setEnds} />
        <div className="dir__wide">
          <Segmented
            value={mode}
            onChange={setMode}
            label={t('Уроки')}
            items={[
              { value: 'day', label: t('Весь день') },
              { value: 'slots', label: t('Выбрать уроки') },
            ]}
          />
        </div>
        {mode === 'slots' && (
          <>
            <Field kind="number" name="slot-from" label={t('С урока')} value={slotFrom} onChange={setSlotFrom} min={1} max={10} />
            <Field kind="number" name="slot-to" label={t('По урок')} value={slotTo} onChange={setSlotTo} min={1} max={10} />
          </>
        )}
        <div className="dir__wide">
          <span className="t-note">{t('Ученики · выбрано {n}', { n: picked.length })}</span>
          <StudentPicks items={items} picked={picked} onChange={setPicked} onSearch={entries.length ? undefined : setSearch} />
        </div>
      </div>
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!olympiadId || !starts || picked.length === 0 || save.isPending}
          onClick={() =>
            save.mutate(
              {
                olympiad: Number(olympiadId),
                students: picked,
                starts,
                ends: ends || starts,
                slot_from: mode === 'slots' ? Number(slotFrom) : null,
                slot_to: mode === 'slots' ? Number(slotTo) : null,
              },
              {
                onSuccess: () => {
                  toast.success(t('Видно академ директору и кураторам'))
                  onClose()
                },
              },
            )
          }
        >
          {t('Сохранить')}
        </Button>
      </div>
    </Modal>
  )
}
