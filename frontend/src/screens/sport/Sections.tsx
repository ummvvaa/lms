/**
 * «Секции» — директор спорта и администратор (макет SSections, 27.10.2026).
 *
 * Сверху переключатель «Запись открыта до…»: пока он выключен, ученики видят
 * только свою секцию, а перенесённые из бота без часа всё равно выбирают час.
 * Слева секции с числом записанных и «N без часа», справа — карточка секции:
 * занятия по часам с полосой заполнения и список учеников часа. Ученика можно
 * перевести в другой час своей параллели, назначить час, убрать из секции
 * и записать самому — и при закрытой записи. Окна записи — `EnrollDialogs`.
 *
 * Печатный QR (05.11.2026): «Скачать QR для печати» отдаёт лист A4 с постоянным
 * кодом секции, «Выпустить новый QR» гасит прежний лист. Код работает, когда
 * у секции задано место; место (координаты и радиус) видит и правит только
 * администратор — в «Изменить секцию».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  useEnrollSettings,
  useReissueQr,
  useRemoveEnrollment,
  useSaveSection,
  useSection,
  useSections,
  type EnrollmentRow,
  type SectionDetail,
  type SlotDraft,
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
import { EnrollDialog, MoveDialog } from './EnrollDialogs'
import { downloadQrSheet } from './printQr'
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
  const [reissuing, setReissuing] = useState(false)
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const slot = data.slots.find((row) => row.id === slotId) ?? data.slots[0]
  // места нет — сервер отвечает, к кому идти; кнопка это и показывает
  const print = () => void downloadQrSheet(data.id, data.title)
  return (
    <DataCard
      className="card--beam"
      title={data.title}
      note={data.address}
      right={
        <span className="dir__acts sport-head">
          <Button variant="outline" size="sm" onClick={print}>
            {t('Скачать QR для печати')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            {t('Изменить секцию')}
          </Button>
          {data.has_location && (
            <RowMenu>
              <RowMenuItem onClick={() => setReissuing(true)}>{t('Выпустить новый QR')}</RowMenuItem>
            </RowMenu>
          )}
        </span>
      }
    >
      {!data.has_location && (
        <p className="t-note sport-why">
          {data.location
            ? t('Место секции не задано — печатный QR не работает. Задайте координаты в «Изменить секцию»')
            : t('Место секции не задано — печатный QR не работает. Обратитесь к администратору')}
        </p>
      )}
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
      {reissuing && <ReissueDialog section={data} onClose={() => setReissuing(false)} onDone={print} />}
    </DataCard>
  )
}

/** «Выпустить новый QR»: прежний лист перестаёт работать сразу — поэтому с подтверждением. */
function ReissueDialog({
  section,
  onClose,
  onDone,
}: {
  section: SectionDetail
  onClose: () => void
  onDone: () => void
}) {
  const reissue = useReissueQr()
  return (
    <Modal title={t('Выпустить новый QR?')} note={section.title} onClose={onClose}>
      <p className="t-note">
        {t(
          'Старый лист перестанет работать сразу: ученики по нему не отметятся. Новый лист скачается — распечатайте его и повесьте вместо старого. Выпуск записывается в журнал изменений.',
        )}
      </p>
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          variant="destructive"
          disabled={reissue.isPending}
          onClick={() =>
            reissue.mutate(section.id, {
              onSuccess: () => {
                toast.success(t('Новый QR выпущен · старый лист больше не работает'))
                onClose()
                onDone()
              },
              onError: fail,
            })
          }
        >
          {t('Выпустить новый')}
        </Button>
      </div>
    </Modal>
  )
}

/** Широта и долгота из строки «43.23, 76.94» — только чтобы открыть карту; проверяет место сервер. */
function mapLink(point: string): string | null {
  const found = /^\s*(-?\d+(?:\.\d+)?)[\s,;]+(-?\d+(?:\.\d+)?)\s*$/.exec(point)
  if (!found) return null
  const [latitude, longitude] = [Number(found[1]), Number(found[2])]
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null
  // Яндекс Карты: метка в точке, сначала долгота, потом широта
  return `https://yandex.ru/maps/?pt=${longitude},${latitude}&z=17&l=map`
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
      {moving && (
        <MoveDialog
          row={moving}
          options={others.map((item) => ({
            value: String(item.id),
            title: t('{slot} · свободно {free} из {total}', {
              slot: slotWords(item),
              free: item.free ?? 0,
              total: item.capacity,
            }),
          }))}
          onClose={() => setMoving(null)}
        />
      )}
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
          options={section.slots
            .filter(
              (slot) =>
                slot.parallel_from <= assigning.student.parallel &&
                assigning.student.parallel <= slot.parallel_to,
            )
            .map((item) => ({
              value: String(item.id),
              title: t('{slot} · свободно {free} из {total}', {
                slot: slotWords(item),
                free: item.free ?? 0,
                total: item.capacity,
              }),
            }))}
          onClose={() => setAssigning(null)}
          assign
        />
      )}
    </div>
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
  // место секции приходит только администратору — у директора спорта этих полей нет
  const place = section.location
  const [point, setPoint] = useState(place?.point ?? '')
  const [radius, setRadius] = useState(place?.radius_m ? String(place.radius_m) : '')
  const map = mapLink(point)
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
      {place && (
        <>
          <span className="t-card">{t('Место секции · для отметки по печатному QR')}</span>
          <div className="sport-place">
            <Field
              name="point"
              label={t('Координаты: широта, долгота')}
              value={point}
              onChange={setPoint}
              placeholder="43.238949, 76.889709"
              hint={t('Скопируйте точку из 2ГИС или Яндекс Карт одной строкой. Пусто — печатного QR у секции нет')}
            />
            <Field
              kind="number"
              name="radius"
              label={t('Радиус, м')}
              value={radius}
              min={1}
              onChange={(value) => setRadius(String(value ?? ''))}
              placeholder={String(place.default_radius_m)}
              hint={t('Пусто — {n} м по правилу школы', { n: place.default_radius_m })}
            />
            {map ? (
              <a className="sport-place__map" href={map} target="_blank" rel="noreferrer">
                {t('Открыть на карте')}
              </a>
            ) : (
              <span className="t-note sport-place__map">
                {point.trim() ? t('Координаты — два числа через запятую') : t('Координаты не заданы')}
              </span>
            )}
          </div>
        </>
      )}
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
                ...(place
                  ? { location: { point: point.trim(), radius_m: radius.trim() ? Number(radius) : null } }
                  : {}),
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
