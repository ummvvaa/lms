/**
 * «Секции» — директор спорта и администратор (макет SSections, 27.10.2026).
 *
 * Сверху переключатель «Запись открыта до…»: пока он выключен, ученики видят
 * только свою секцию, а перенесённые из бота без часа всё равно выбирают час.
 * Слева секции с числом записанных и «N без часа», справа — карточка секции:
 * занятия по часам с полосой заполнения и список учеников часа. Ученика можно
 * перевести в другой час своей параллели, назначить час, убрать из секции
 * и записать самому — и при закрытой записи.
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  useEnrollSettings,
  useEnrollStudent,
  useMoveEnrollment,
  useRemoveEnrollment,
  useSaveSection,
  useSection,
  useSections,
  useStudentSearch,
  type EnrollmentRow,
  type SectionDetail,
  type SlotDraft,
  type SlotRow,
} from '../../api/sport'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t, tk } from '../../i18n'
import { formatDateTimeLong, formatDayMonth } from '../../lib/format'
import { WEEKDAYS, slotTime, slotWords } from './words'
import '../directors/directors.css'
import './sport.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

export default function Sections() {
  const { data, isLoading, error } = useSections()
  const [params, setParams] = useSearchParams()
  const [enrolling, setEnrolling] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const picked = Number(params.get('open')) || data.rows[0]?.id || null

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Секции')}
        subtitle={t('Расписание, лимиты на каждый час и кто куда записан')}
        actions={
          <>
            <Button
              variant="outline"
              onClick={() =>
                downloadFile('/sport/sections/export/', t('Секции.xlsx'))
                  .then(() => toast.success(t('Файл xlsx скачан · лист на каждую секцию')))
                  .catch(fail)
              }
            >
              {t('Скачать Excel')}
            </Button>
            <Button onClick={() => setEnrolling(true)}>{t('Записать ученика')}</Button>
          </>
        }
      />
      <EnrollWindow open={data.settings.open} until={data.settings.enroll_until} />
      <div className="sport-pair">
        <DataCard title={t('Секции')} count={data.rows.length}>
          <div className="sport-today">
            {data.rows.map((row) => (
              <Button
                key={row.id}
                variant="ghost"
                className={`sport-slot${row.id === picked ? ' sport-slot--on' : ''}`}
                aria-pressed={row.id === picked}
                onClick={() => setParams({ open: String(row.id) }, { replace: true })}
              >
                <span className="sport-slot__line">
                  <b>{row.title}</b>
                  {row.no_hour > 0 && (
                    <Chip tone="warn" size="sm">
                      {t('{n} без часа', { n: row.no_hour })}
                    </Chip>
                  )}
                </span>
                <span className="t-note num">
                  {t('{n} из {total} мест', { n: row.enrolled, total: row.capacity })}
                </span>
                <Bar percent={(row.enrolled * 100) / Math.max(1, row.capacity)} />
              </Button>
            ))}
          </div>
        </DataCard>
        {picked !== null && <SectionCard id={picked} key={picked} />}
      </div>
      {enrolling && <EnrollDialog onClose={() => setEnrolling(false)} />}
    </div>
  )
}

/** «Запись открыта до…»: переключатель и дата; выключено — ученики видят только свою секцию. */
function EnrollWindow({ open, until }: { open: boolean; until: string | null }) {
  const save = useEnrollSettings()
  const [editing, setEditing] = useState(false)
  const [date, setDate] = useState(until ? until.slice(0, 10) : '')
  const [time, setTime] = useState(until ? until.slice(11, 16) : '23:59')
  const apply = (value: string | null) =>
    save.mutate(value, {
      onSuccess: (next) => {
        setEditing(false)
        toast.success(
          next.open
            ? t('Запись открыта · ученики видят выбор секции')
            : t('Запись закрыта · ученики видят только свою секцию'),
        )
      },
      onError: fail,
    })
  return (
    <section className="card card-pad sport-window">
      <Switch
        checked={open || editing}
        aria-label={t('Запись открыта')}
        onCheckedChange={(next) => (next ? setEditing(true) : apply(null))}
      />
      <span className="dir__what">
        <b>{open ? t('Запись открыта') : t('Запись закрыта')}</b>
        <span className="t-note">
          {open
            ? t('Ученики выбирают секцию и час, могут отменить и выбрать другую')
            : t('Ученики видят только свою секцию. Выбор часа для тех, кто без часа, остаётся')}
        </span>
      </span>
      {editing ? (
        <span className="sport-window__form">
          <Field kind="date" name="enroll-date" label={t('До даты')} value={date} onChange={setDate} />
          <Field kind="time" name="enroll-time" label={t('Время')} value={time} onChange={setTime} />
          <Button disabled={!date || save.isPending} onClick={() => apply(`${date}T${time || '23:59'}:00`)}>
            {t('Сохранить')}
          </Button>
          <Button variant="ghost" onClick={() => setEditing(false)}>
            {t('Отмена')}
          </Button>
        </span>
      ) : (
        <span className="dir__acts">
          {open && until && (
            <Chip tone="good" size="sm">
              {t('до {when}', { when: formatDateTimeLong(until) })}
            </Chip>
          )}
          {open && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {t('Изменить дату')}
            </Button>
          )}
        </span>
      )}
    </section>
  )
}

function SectionCard({ id }: { id: number }) {
  const { data, isLoading, error } = useSection(id)
  const [slotId, setSlotId] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const slot = data.slots.find((row) => row.id === slotId) ?? data.slots[0]
  return (
    <DataCard
      className="card--beam"
      title={data.title}
      note={data.address}
      right={
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          {t('Изменить секцию')}
        </Button>
      }
    >
      <div className="sport-slots">
        {data.slots.map((row) => {
          const taken = row.taken ?? 0
          return (
            <Button
              key={row.id}
              variant="ghost"
              className={`sport-slot${row.id === slot?.id ? ' sport-slot--on' : ''}`}
              aria-pressed={row.id === slot?.id}
              onClick={() => setSlotId(row.id)}
            >
              <b className="sport-slot__head">{slotWords(row)}</b>
              <span className="t-note num">
                {[
                  t('{n} из {total}', { n: taken, total: row.capacity }),
                  t('параллели {grades}', { grades: `${row.parallel_from}–${row.parallel_to}` }),
                  row.room,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <Bar percent={(taken * 100) / Math.max(1, row.capacity)} />
            </Button>
          )
        })}
      </div>
      {data.no_hour.length > 0 && <NoHour section={data} />}
      {slot ? (
        <SlotStudents section={data} slot={slot} />
      ) : (
        <EmptyNote what={tk('у секции нет занятий')} who={tk('добавьте занятие в «Изменить секцию»')} />
      )}
      {editing && <EditSectionDialog section={data} onClose={() => setEditing(false)} />}
    </DataCard>
  )
}

function sourceWords(row: EnrollmentRow): string {
  return t('{date}, {source}', {
    date: formatDayMonth(row.enrolled_at),
    source: row.source === 'bot' ? t('бот') : t('LMS'),
  })
}

function SlotStudents({ section, slot }: { section: SectionDetail; slot: SectionDetail['slots'][number] }) {
  const remove = useRemoveEnrollment()
  const [moving, setMoving] = useState<EnrollmentRow | null>(null)
  const [removing, setRemoving] = useState<EnrollmentRow | null>(null)
  const others = section.slots.filter(
    (row) =>
      row.id !== slot.id && row.parallel_from === slot.parallel_from && row.parallel_to === slot.parallel_to,
  )
  return (
    <div className="sport-list">
      <div className="sport-list__head">
        <span className="t-card">
          {t('{day}, {time} · параллели {grades}', {
            day: slot.day,
            time: slotTime(slot),
            grades: `${slot.parallel_from}–${slot.parallel_to}`,
          })}
        </span>
        <Chip className="num">{slot.students.length}</Chip>
      </div>
      {slot.students.length === 0 ? (
        <EmptyNote what={tk('на этот час никто не записан')} who={tk('ученики записываются в «Спорте»')} />
      ) : (
        <div className="dir__rows">
          <ShowAll limit={5}>
            {slot.students.map((row) => (
              <div key={row.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{row.student.short_name}</b>
                  <span className="t-note">
                    {[t('{n} параллель', { n: row.student.parallel }), row.student.group, sourceWords(row)]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                <span className="num sport-pct">
                  {row.percent === null ? t('нет занятий') : `${row.percent}%`}
                </span>
                <span className="dir__acts">
                  <RowMenu>
                    {others.length > 0 && (
                      <RowMenuItem onClick={() => setMoving(row)}>{t('Перевести в другой час')}</RowMenuItem>
                    )}
                    <RowMenuItem onClick={() => setRemoving(row)}>{t('Убрать из секции')}</RowMenuItem>
                  </RowMenu>
                </span>
              </div>
            ))}
          </ShowAll>
        </div>
      )}
      {moving && <MoveDialog row={moving} slots={others} onClose={() => setMoving(null)} />}
      {removing && (
        <Modal
          title={t('Убрать из секции?')}
          note={removing.student.full_name}
          onClose={() => setRemoving(null)}
        >
          <p className="t-note">{t('Запись закроется, место освободится. История посещений останется.')}</p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setRemoving(null)}>
              {t('Отмена')}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(removing.id, {
                  onSuccess: () => {
                    toast.success(t('Ученик убран из секции · место освободилось'))
                    setRemoving(null)
                  },
                  onError: fail,
                })
              }
            >
              {t('Убрать')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

/** Перенесённые из бота без часа: ученик видит «Выбери время», директор может назначить час сам. */
function NoHour({ section }: { section: SectionDetail }) {
  const [assigning, setAssigning] = useState<EnrollmentRow | null>(null)
  return (
    <div className="sport-list sport-list--warn">
      <div className="sport-list__head">
        <span className="t-card">{t('Перенесены из бота, час не выбран')}</span>
        <Chip tone="warn" className="num">
          {section.no_hour.length}
        </Chip>
      </div>
      <p className="t-note">{t('ученик видит плашку «Выбери время»; можно назначить час самому')}</p>
      <div className="dir__rows">
        <ShowAll limit={5}>
          {section.no_hour.map((row) => (
            <div key={row.id} className="dir__row">
              <span className="dir__what">
                <b className="dir__name">{row.student.short_name}</b>
                <span className="t-note">
                  {[t('{n} параллель', { n: row.student.parallel }), row.student.group, sourceWords(row)]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <span />
              <span className="dir__acts">
                <Button variant="outline" size="sm" onClick={() => setAssigning(row)}>
                  {t('Назначить час')}
                </Button>
              </span>
            </div>
          ))}
        </ShowAll>
      </div>
      {assigning && (
        <MoveDialog
          row={assigning}
          slots={section.slots.filter(
            (slot) =>
              slot.parallel_from <= assigning.student.parallel &&
              assigning.student.parallel <= slot.parallel_to,
          )}
          onClose={() => setAssigning(null)}
          assign
        />
      )}
    </div>
  )
}

function MoveDialog({
  row,
  slots,
  onClose,
  assign = false,
}: {
  row: EnrollmentRow
  slots: SlotRow[]
  onClose: () => void
  assign?: boolean
}) {
  const move = useMoveEnrollment()
  const [slot, setSlot] = useState(String(slots[0]?.id ?? ''))
  return (
    <Modal
      title={assign ? t('Назначить час') : t('Перевести в другой час')}
      note={row.student.full_name}
      onClose={onClose}
    >
      <Field
        kind="select"
        name="slot"
        label={t('Час занятия')}
        value={slot}
        onChange={setSlot}
        options={slots.map((item) => ({
          value: String(item.id),
          title: t('{slot} · свободно {free} из {total}', {
            slot: slotWords(item),
            free: item.free ?? 0,
            total: item.capacity,
          }),
        }))}
      />
      {move.error && <ErrorNote error={move.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!slot || move.isPending}
          onClick={() =>
            move.mutate(
              { id: row.id, slot: Number(slot) },
              {
                onSuccess: () => {
                  toast.success(assign ? t('Час назначен · ученик увидит его у себя') : t('Ученик переведён'))
                  onClose()
                },
              },
            )
          }
        >
          {assign ? t('Назначить') : t('Перевести')}
        </Button>
      </div>
    </Modal>
  )
}

/** Директор записывает сам — и при закрытой записи: поиск ученика и час его параллели. */
function EnrollDialog({ onClose }: { onClose: () => void }) {
  const sections = useSections()
  const enroll = useEnrollStudent()
  const [query, setQuery] = useState('')
  const found = useStudentSearch(query)
  const [student, setStudent] = useState<number | null>(null)
  const [slot, setSlot] = useState('')
  const hit = found.data?.rows.find((row) => row.id === student) ?? null
  const options = useMemo(
    () =>
      (sections.data?.rows ?? []).flatMap((section) =>
        section.slots
          .filter((row) => hit && row.parallel_from <= hit.parallel && hit.parallel <= row.parallel_to)
          .map((row) => ({
            value: String(row.id),
            title: t('{section}, {slot} · свободно {free}', {
              section: section.title,
              slot: slotWords(row),
              free: row.free ?? 0,
            }),
          })),
      ),
    [sections.data, hit],
  )
  return (
    <Modal
      title={t('Записать ученика')}
      note={t('и при закрытой записи · одна секция на ученика')}
      onClose={onClose}
    >
      <Field
        name="search"
        label={t('Ученик')}
        value={query}
        onChange={setQuery}
        placeholder={t('Фамилия или группа')}
        autoFocus
      />
      {query.trim().length >= 2 && (
        <div className="dir__rows dir__picks">
          {(found.data?.rows ?? []).map((row) => (
            <div key={row.id} className="dir__row">
              <span className="dir__what">
                <b className="dir__name">{row.short_name}</b>
                <span className="t-note">
                  {[row.group, row.section ? `${row.section} ${row.slot}`.trim() : t('не записан')].join(
                    ' · ',
                  )}
                </span>
              </span>
              <span />
              <span className="dir__acts">
                <Button
                  variant={row.id === student ? 'secondary' : 'outline'}
                  size="sm"
                  aria-pressed={row.id === student}
                  onClick={() => {
                    setStudent(row.id)
                    setSlot('')
                  }}
                >
                  {row.id === student ? t('выбран') : t('Выбрать')}
                </Button>
              </span>
            </div>
          ))}
          {found.data && found.data.rows.length === 0 && <EmptyNote what={tk('никого не нашли')} />}
        </div>
      )}
      {hit && (
        <Field
          kind="select"
          name="slot"
          label={t('Час занятия')}
          value={slot}
          onChange={setSlot}
          placeholder={t('Выберите час')}
          options={options}
          hint={
            hit.section
              ? t('прежняя запись в секцию «{section}» закроется', { section: hit.section })
              : undefined
          }
        />
      )}
      {enroll.error && <ErrorNote error={enroll.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!student || !slot || enroll.isPending}
          onClick={() =>
            enroll.mutate(
              { student: student as number, slot: Number(slot) },
              {
                onSuccess: () => {
                  toast.success(t('Ученик записан'))
                  onClose()
                },
              },
            )
          }
        >
          {t('Записать')}
        </Button>
      </div>
    </Modal>
  )
}

type Draft = SlotDraft & { taken: number }

/**
 * «Изменить секцию»: адрес и занятия. Убрать занятие с записанными можно,
 * только выбрав, куда их перевести, — или оставить «без часа»: тогда ученики
 * увидят «Выбери время».
 */
function EditSectionDialog({ section, onClose }: { section: SectionDetail; onClose: () => void }) {
  const save = useSaveSection()
  const [address, setAddress] = useState(section.address)
  const [slots, setSlots] = useState<Draft[]>(() =>
    section.slots.map((row) => ({
      id: row.id,
      weekday: row.weekday,
      starts: row.starts,
      ends: row.ends,
      parallel_from: row.parallel_from,
      parallel_to: row.parallel_to,
      room: row.room,
      capacity: row.capacity,
      taken: row.taken ?? 0,
    })),
  )
  const [moves, setMoves] = useState<Record<string, string>>({})
  const removed = section.slots.filter(
    (row) => !slots.some((draft) => draft.id === row.id) && (row.taken ?? 0) > 0,
  )
  const change = (index: number, patch: Partial<Draft>) =>
    setSlots((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  const grades = [
    { value: '8-9', title: t('параллели 8–9') },
    { value: '10-11', title: t('параллели 10–11') },
    { value: '8-11', title: t('параллели 8–11') },
  ]
  return (
    <Modal title={t('Изменить секцию')} note={section.title} onClose={onClose} wide>
      <Field name="address" label={t('Адрес площадки')} value={address} onChange={setAddress} />
      <span className="t-card">{t('Занятия · лимит на каждый час')}</span>
      <div className="sport-edit">
        {slots.map((row, index) => (
          <div key={row.id ?? row.key} className="sport-edit__row">
            <Field
              kind="select"
              name={`day-${index}`}
              label={t('День')}
              value={String(row.weekday)}
              onChange={(value) => change(index, { weekday: Number(value) })}
              options={WEEKDAYS.map((label, value) => ({ value: String(value), title: t(label) }))}
            />
            <Field
              kind="time"
              name={`starts-${index}`}
              label={t('Начало')}
              value={row.starts}
              onChange={(value) => change(index, { starts: value })}
            />
            <Field
              kind="time"
              name={`ends-${index}`}
              label={t('Конец')}
              value={row.ends}
              onChange={(value) => change(index, { ends: value })}
            />
            <Field
              kind="select"
              name={`grades-${index}`}
              label={t('Параллели')}
              value={`${row.parallel_from}-${row.parallel_to}`}
              onChange={(value) => {
                const [from, to] = value.split('-').map(Number)
                change(index, { parallel_from: from, parallel_to: to })
              }}
              options={grades}
            />
            <Field
              kind="number"
              name={`capacity-${index}`}
              label={t('Мест')}
              value={row.capacity}
              min={1}
              onChange={(value) => change(index, { capacity: Number(value) })}
            />
            <Field
              name={`room-${index}`}
              label={t('Кабинет')}
              value={row.room}
              onChange={(value) => change(index, { room: value })}
            />
            <Button
              variant="ghost"
              size="sm"
              className="sport-edit__drop"
              onClick={() => setSlots((rows) => rows.filter((_row, i) => i !== index))}
            >
              {t('Убрать')}
            </Button>
          </div>
        ))}
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          setSlots((rows) => [
            ...rows,
            {
              key: `new-${rows.length}-${Date.now()}`,
              weekday: 5,
              starts: '12:00',
              ends: '13:00',
              parallel_from: 10,
              parallel_to: 11,
              room: '',
              capacity: 20,
              taken: 0,
            },
          ])
        }
      >
        {t('Добавить занятие')}
      </Button>
      {removed.map((row) => (
        <Field
          key={row.id}
          kind="select"
          name={`move-${row.id}`}
          label={t('Записаны на {slot} — {n}: куда перевести', { slot: slotWords(row), n: row.taken ?? 0 })}
          value={moves[String(row.id)] ?? ''}
          onChange={(value) => setMoves((all) => ({ ...all, [String(row.id)]: value }))}
          placeholder={t('Оставить без часа — ученики выберут сами')}
          options={slots
            .filter(
              (draft) => draft.parallel_from <= row.parallel_from && row.parallel_to <= draft.parallel_to,
            )
            .map((draft) => ({
              value: String(draft.id ?? draft.key),
              title: t('{day} {time}', {
                day: t(WEEKDAYS[draft.weekday]),
                time: `${draft.starts}–${draft.ends}`,
              }),
            }))}
        />
      ))}
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!address.trim() || save.isPending}
          onClick={() =>
            save.mutate(
              {
                id: section.id,
                address,
                slots: slots.map((row) => ({
                  id: row.id,
                  key: row.key,
                  weekday: row.weekday,
                  starts: row.starts,
                  ends: row.ends,
                  parallel_from: row.parallel_from,
                  parallel_to: row.parallel_to,
                  room: row.room,
                  capacity: row.capacity,
                })),
                moves: Object.fromEntries(Object.entries(moves).map(([key, value]) => [key, value || null])),
              },
              {
                onSuccess: () => {
                  toast.success(t('Секция сохранена'))
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
