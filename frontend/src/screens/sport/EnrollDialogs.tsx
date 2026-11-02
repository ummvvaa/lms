/**
 * Окна записи директора спорта: «Записать ученика» и «Перевести / Назначить час».
 *
 * Одни и те же на экранах «Секции» и «Ученики секций». Сверх предела секций
 * или лимита часа сервер отвечает «можно, но подтвердите» — окно показывает
 * предупреждения и вторую кнопку «Записать всё равно». Пересечение часов
 * и чужая параллель — отказ, его текст виден в окне.
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  confirmWarnings,
  useEnrollStudent,
  useMoveEnrollment,
  useSections,
  useStudentSearch,
  type SectionRow,
  type SectionStudent,
} from '../../api/sport'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { EmptyNote, ErrorNote } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { slotWords } from './words'

export interface SlotOption {
  value: string
  title: string
}

/** Часы всех секций для параллели ученика: «Теннис, Сб 12:00–13:00 · свободно 3». */
export function slotOptions(
  sections: SectionRow[],
  parallel: number,
  { exclude, section }: { exclude?: number | null; section?: number } = {},
): SlotOption[] {
  return sections
    .filter((row) => section === undefined || row.id === section)
    .flatMap((row) =>
      row.slots
        .filter((slot) => slot.parallel_from <= parallel && parallel <= slot.parallel_to && slot.id !== exclude)
        .map((slot) => ({
          value: String(slot.id),
          title: t('{section}, {slot} · свободно {free}', {
            section: row.title,
            slot: slotWords(slot),
            free: slot.free ?? 0,
          }),
        })),
    )
}

/** Предупреждения «сверх предела» тихой янтарной строкой и кнопка «… всё равно». */
function Warnings({ items }: { items: string[] }) {
  return (
    <div className="sport-warn">
      {items.map((item) => (
        <p key={item} className="t-note">
          {item}
        </p>
      ))}
    </div>
  )
}

/** Отказ — текстом; «подтвердите» — предупреждениями. */
function Outcome({ error }: { error: unknown }) {
  const warnings = confirmWarnings(error)
  if (warnings) return <Warnings items={warnings} />
  return error ? <ErrorNote error={error} /> : null
}

export function MoveDialog({
  row,
  options,
  onClose,
  assign = false,
  anySection = false,
}: {
  row: { id: number; student: SectionStudent }
  options: SlotOption[]
  onClose: () => void
  assign?: boolean
  /** перевод и в другую секцию: прежняя запись закроется */
  anySection?: boolean
}) {
  const move = useMoveEnrollment()
  const [slot, setSlot] = useState(options[0]?.value ?? '')
  const warned = confirmWarnings(move.error) !== null
  const send = (force: boolean) =>
    move.mutate(
      { id: row.id, slot: Number(slot), force },
      {
        onSuccess: () => {
          toast.success(assign ? t('Час назначен · ученик увидит его у себя') : t('Ученик переведён'))
          onClose()
        },
      },
    )
  return (
    <Modal
      title={assign ? t('Назначить час') : anySection ? t('Перевести') : t('Перевести в другой час')}
      note={row.student.full_name}
      onClose={onClose}
    >
      {options.length === 0 ? (
        <EmptyNote what={tk('других часов для параллели ученика нет')} />
      ) : (
        <Field
          kind="select"
          name="slot"
          label={t('Час занятия')}
          value={slot}
          onChange={(value) => {
            setSlot(value)
            move.reset()
          }}
          options={options}
          hint={anySection ? t('в другую секцию — прежняя запись закроется, история останется') : undefined}
        />
      )}
      <Outcome error={move.error} />
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button disabled={!slot || move.isPending} onClick={() => send(warned)}>
          {warned
            ? t('Всё равно перевести')
            : assign
              ? t('Назначить')
              : t('Перевести')}
        </Button>
      </div>
    </Modal>
  )
}

/**
 * Директор записывает сам — и при закрытой записи: поиск ученика и час его
 * параллели. Прежние секции ученика остаются; ученик уже выбран — поиска нет.
 */
export function EnrollDialog({ onClose, student: preset }: { onClose: () => void; student?: SectionStudent }) {
  const sections = useSections()
  const enroll = useEnrollStudent()
  const [query, setQuery] = useState('')
  const found = useStudentSearch(preset ? '' : query)
  const [student, setStudent] = useState<number | null>(preset?.id ?? null)
  const [slot, setSlot] = useState('')
  const hit = found.data?.rows.find((row) => row.id === student) ?? null
  const parallel = preset?.parallel ?? hit?.parallel ?? null
  const options = useMemo(
    () => (parallel === null ? [] : slotOptions(sections.data?.rows ?? [], parallel)),
    [sections.data, parallel],
  )
  const warned = confirmWarnings(enroll.error) !== null
  const send = (force: boolean) =>
    enroll.mutate(
      { student: student as number, slot: Number(slot), force },
      {
        onSuccess: () => {
          toast.success(t('Ученик записан'))
          onClose()
        },
      },
    )
  return (
    <Modal
      title={preset ? t('Записать ещё в секцию') : t('Записать ученика')}
      note={preset ? preset.full_name : t('и при закрытой записи · прежние секции ученика остаются')}
      onClose={onClose}
    >
      {!preset && (
        <Field
          name="search"
          label={t('Ученик')}
          value={query}
          onChange={setQuery}
          placeholder={t('Фамилия или группа')}
          autoFocus
        />
      )}
      {!preset && query.trim().length >= 2 && (
        <div className="dir__rows dir__picks">
          {(found.data?.rows ?? []).map((row) => (
            <div key={row.id} className="dir__row">
              <span className="dir__what">
                <b className="dir__name">{row.short_name}</b>
                <span className="t-note">
                  {[
                    row.group,
                    row.sections.length
                      ? row.sections.map((e) => `${e.section_title} ${e.slot_title}`.trim()).join(', ')
                      : t('не записан'),
                  ].join(' · ')}
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
                    enroll.reset()
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
      {parallel !== null && (
        <Field
          kind="select"
          name="slot"
          label={t('Час занятия')}
          value={slot}
          onChange={(value) => {
            setSlot(value)
            enroll.reset()
          }}
          placeholder={t('Выберите час')}
          options={options}
        />
      )}
      <Outcome error={enroll.error} />
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button disabled={!student || !slot || enroll.isPending} onClick={() => send(warned)}>
          {warned ? t('Всё равно записать') : t('Записать')}
        </Button>
      </div>
    </Modal>
  )
}
