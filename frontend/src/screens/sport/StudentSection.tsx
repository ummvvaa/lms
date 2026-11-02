/**
 * «Мои секции» ученика (макет StSections, 27.10.2026; несколько секций — 02.11.2026).
 *
 * На каждую запись — своя карточка: час, ближайшее занятие, адрес, посещение
 * и свои отметки, при открытой записи — «Выйти» и «Сменить время» именно этой
 * секции. Перенесённый из бота без часа — «Выбери время» с часами своей
 * параллели. При открытой записи и свободном месте в пределе — «Записаться
 * ещё в секцию»: час, совпадающий с другой своей секцией, закрыт с причиной.
 * Ученик видит только себя: чужих имён, средних и ярлыков здесь нет.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useMySection,
  useMySectionAction,
  type MyEnrollment,
  type MySectionData,
  type SlotRow,
} from '../../api/sport'
import Modal from '../../components/Modal'
import { ShowAll } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDateLong, formatDateTimeLong, formatTime, formatWeekday } from '../../lib/format'
import { slotLong, slotWords } from './words'
import '../directors/directors.css'
import './sport.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

export default function StudentSection() {
  const { data, isLoading, error } = useMySection()
  // что выбирает ученик: ещё одну секцию (`'new'`) или другой час своей (id секции)
  const [choosing, setChoosing] = useState<'new' | number | null>(null)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const mine = data.enrollments
  if (choosing !== null && data.open)
    return (
      <Choose
        data={data}
        section={choosing === 'new' ? undefined : choosing}
        onBack={() => setChoosing(null)}
      />
    )
  if (mine.length === 0 && !data.open)
    return (
      <DataCard
        title={t('Запись на секции закрыта')}
        note={t(
          'Ты не записан ни в одну секцию. Если хочешь заниматься, подойди к директору спорта — он может записать тебя сам',
        )}
      />
    )
  if (mine.length === 0) return <Choose data={data} />
  const more = data.open && mine.length < data.max
  return (
    <div className="sport-mine">
      {mine.map((row, index) =>
        row.slot === null ? (
          <ChooseHour key={row.id} data={data} mine={row} />
        ) : (
          <MySection
            key={row.id}
            data={data}
            mine={row}
            main={index === 0}
            onChange={() => setChoosing(row.section)}
          />
        ),
      )}
      {data.open ? (
        <DataCard
          title={more ? t('Ещё одна секция') : t('Секций — {n} из {max}', { n: mine.length, max: data.max })}
          note={
            more
              ? t('Можно ходить в несколько секций, если часы не совпадают · не больше {max}', {
                  max: data.max,
                })
              : t('Больше секций по правилам школы нельзя · можно выйти из одной и выбрать другую')
          }
          right={more && <Button onClick={() => setChoosing('new')}>{t('Записаться ещё в секцию')}</Button>}
        />
      ) : (
        <p className="t-note">
          {t('Запись закрыта · сменить или добавить секцию можно через директора спорта')}
        </p>
      )}
    </div>
  )
}

function MySection({
  data,
  mine,
  main,
  onChange,
}: {
  data: MySectionData
  mine: MyEnrollment
  main: boolean
  onChange: () => void
}) {
  const { leave } = useMySectionAction()
  const [leaving, setLeaving] = useState(false)
  const slot = mine.slot!
  return (
    <div className="lay-main">
      <DataCard
        className={main ? 'card--beam' : undefined}
        title={mine.section_title}
        note={t('Моя секция')}
        right={
          <Chip tone="good" size="sm">
            {t('записан')}
          </Chip>
        }
      >
        <div className="dir__lines">
          <div className="dir__line">
            <span>{t('Время')}</span>
            <b>{slotLong(slot)}</b>
          </div>
          {mine.next_at && (
            <div className="dir__line">
              <span>{t('Ближайшее занятие')}</span>
              <b>
                {t('{day}, {date}', {
                  day: formatWeekday(mine.next_at, 'short'),
                  date: formatDateLong(mine.next_at),
                })}
              </b>
            </div>
          )}
          <div className="dir__line">
            <span>{t('Адрес')}</span>
            <b>{[mine.address, slot.room].filter(Boolean).join(' · ')}</b>
          </div>
          <div className="dir__line">
            <span>{t('Посещение')}</span>
            <b className="num">{mine.percent === null ? t('занятий ещё не было') : `${mine.percent}%`}</b>
          </div>
        </div>
        <p className="t-note">
          {t('На занятии наведи камеру телефона на QR у директора спорта — откроется LMS и отметит тебя')}
        </p>
        {data.open ? (
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setLeaving(true)}>
              {t('Выйти из секции')}
            </Button>
            <Button onClick={onChange}>{t('Сменить время')}</Button>
          </div>
        ) : (
          <p className="t-note">
            {t('Запись закрыта · выйти или сменить время можно через директора спорта')}
          </p>
        )}
      </DataCard>
      <DataCard
        title={t('Мои отметки')}
        right={<Chip className="num">{t('{came} из {n}', { came: mine.came, n: mine.marks.length })}</Chip>}
        empty={mine.marks.length === 0 && t('занятий ещё не было')}
      >
        <div className="dir__rows">
          <ShowAll limit={5}>
            {mine.marks.map((mark) => (
              <div key={mark.date} className="dir__row">
                <span className="dir__what">
                  <b>
                    {t('{day}, {date}', {
                      day: formatWeekday(mark.date, 'short'),
                      date: formatDateLong(mark.date),
                    })}
                  </b>
                  <span className="t-note">
                    {mark.came
                      ? mark.method === 'manual'
                        ? t('вручную')
                        : mark.at
                          ? t('по QR · {time}', { time: formatTime(mark.at) })
                          : t('по QR')
                      : t('отметки нет')}
                  </span>
                </span>
                <Chip tone={mark.came ? 'good' : 'bad'} size="sm">
                  {mark.came ? t('был') : t('не был')}
                </Chip>
                <span />
              </div>
            ))}
          </ShowAll>
        </div>
      </DataCard>
      {leaving && (
        <Modal title={t('Выйти из секции?')} note={mine.section_title} onClose={() => setLeaving(false)}>
          <p className="t-note">{t('Место освободится. Пока запись открыта, можно записаться снова')}</p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setLeaving(false)}>
              {t('Отмена')}
            </Button>
            <Button
              variant="destructive"
              disabled={leave.isPending}
              onClick={() =>
                leave.mutate(mine.section, {
                  onSuccess: () => {
                    toast.success(t('Ты вышел из секции · место освободилось'))
                    setLeaving(false)
                  },
                  onError: fail,
                })
              }
            >
              {t('Выйти')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

/** Перенесён из бота без часа: выбрать час своей параллели — и при закрытой записи. */
function ChooseHour({ data, mine }: { data: MySectionData; mine: MyEnrollment }) {
  const { enroll } = useMySectionAction()
  const slots = data.sections.find((row) => row.id === mine.section)?.slots ?? []
  return (
    <DataCard
      className="card--beam"
      title={t('Ты записан на {section} · выбери время занятия', {
        section: mine.section_title.toLocaleLowerCase(),
      })}
      note={mine.address}
      right={
        <Chip tone="warn" size="sm">
          {t('нужно выбрать час')}
        </Chip>
      }
    >
      <div className="dir__rows">
        {slots.map((slot) => (
          <SlotLine
            key={slot.id}
            slot={slot}
            busy={enroll.isPending}
            onPick={() =>
              enroll.mutate(slot.id, {
                onSuccess: () =>
                  toast.success(
                    t('Время выбрано · {section}, {slot}', {
                      section: mine.section_title,
                      slot: slotLong(slot),
                    }),
                  ),
                onError: fail,
              })
            }
            action={t('Выбрать')}
          />
        ))}
      </div>
      <p className="t-note">{t('Пока час не выбран, отметиться на занятии не получится')}</p>
    </DataCard>
  )
}

function SlotLine({
  slot,
  onPick,
  busy,
  action,
}: {
  slot: SlotRow & { clash?: string }
  onPick: () => void
  busy: boolean
  action: string
}) {
  const free = slot.free ?? 0
  const clash = slot.clash ?? ''
  return (
    <div className="dir__row">
      <span className="dir__what">
        <b>{slotLong(slot)}</b>
        <span className="t-note">
          {[
            slot.room,
            clash
              ? t('в это время у тебя {clash}', { clash })
              : t('свободно {n} из {total}', { n: free, total: slot.capacity }),
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </span>
      {clash ? (
        <Chip tone="neutral" size="sm">
          {t('время занято')}
        </Chip>
      ) : free === 0 ? (
        <Chip tone="neutral" size="sm">
          {t('мест нет')}
        </Chip>
      ) : (
        <span />
      )}
      <span className="dir__acts">
        {free > 0 && !clash && (
          <Button variant="outline" size="sm" disabled={busy} onClick={onPick}>
            {action}
          </Button>
        )}
      </span>
    </div>
  )
}

/**
 * Запись открыта: секции со слотами своей параллели и свободными местами.
 * `section` — сменить время своей секции: показаны только её часы.
 */
function Choose({ data, section, onBack }: { data: MySectionData; section?: number; onBack?: () => void }) {
  const { enroll } = useMySectionAction()
  const [confirm, setConfirm] = useState<{ section: string; slot: SlotRow } | null>(null)
  const own = new Set(data.enrollments.map((row) => row.section))
  // ещё одна секция — без своих; смена времени — только своя
  const shown = data.sections.filter((row) => (section === undefined ? !own.has(row.id) : row.id === section))
  const picked = new Set(data.enrollments.map((row) => row.slot?.id).filter(Boolean))
  return (
    <>
      <DataCard
        title={section === undefined ? t('Выбери секцию и время') : t('Выбери другое время')}
        note={[
          data.enroll_until
            ? t('запись открыта до {when}', { when: formatDateTimeLong(data.enroll_until) })
            : '',
          t('Секций на ученика — не больше {max}, часы не должны совпадать', { max: data.max }),
        ]
          .filter(Boolean)
          .join(' · ')}
        right={
          onBack && (
            <Button variant="ghost" size="sm" onClick={onBack}>
              {t('Отмена')}
            </Button>
          )
        }
      >
        {shown.length === 0 && <EmptyNote what={tk('для твоей параллели занятий нет')} />}
      </DataCard>
      <div className="sport-choose">
        {shown.map((row) => (
          <DataCard key={row.id} title={row.title} note={row.address}>
            <div className="dir__rows">
              {row.slots.map((slot) => (
                <SlotLine
                  key={slot.id}
                  slot={slot}
                  busy={enroll.isPending}
                  onPick={() => setConfirm({ section: row.title, slot })}
                  action={
                    picked.has(slot.id)
                      ? t('выбрано')
                      : section === undefined
                        ? t('Записаться')
                        : t('Выбрать')
                  }
                />
              ))}
            </div>
          </DataCard>
        ))}
      </div>
      {confirm && (
        <Modal
          title={t('Записаться?')}
          note={t('{section}, {slot}', { section: confirm.section, slot: slotWords(confirm.slot) })}
          onClose={() => setConfirm(null)}
        >
          <p className="t-note">{t('Пока запись открыта, можно выйти и выбрать другую секцию или время')}</p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setConfirm(null)}>
              {t('Отмена')}
            </Button>
            <Button
              disabled={enroll.isPending}
              onClick={() =>
                enroll.mutate(confirm.slot.id, {
                  onSuccess: () => {
                    toast.success(
                      t('Ты записан · {section}, {slot}', {
                        section: confirm.section,
                        slot: slotLong(confirm.slot),
                      }),
                    )
                    setConfirm(null)
                    onBack?.()
                  },
                  onError: fail,
                })
              }
            >
              {t('Записаться')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
