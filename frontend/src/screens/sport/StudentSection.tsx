/**
 * «Секция» ученика (макет StSections, 27.10.2026). Четыре состояния:
 * записан — своя секция, час, ближайшее занятие, адрес, посещение и свои
 * отметки, при открытой записи — «Выйти» и «Сменить»; перенесён из бота
 * без часа — «Выбери время» с часами своей параллели; не записан при
 * открытой записи — секции со свободными местами; при закрытой — одна строка.
 * Ученик видит только себя: чужих имён, средних и ярлыков здесь нет.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useMySection, useMySectionAction, type MySectionData, type SlotRow } from '../../api/sport'
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
  const [changing, setChanging] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const mine = data.enrollment
  if (mine && mine.slot === null) return <ChooseHour data={data} />
  if (mine && !changing) return <MySection data={data} onChange={() => setChanging(true)} />
  if (!data.open)
    return (
      <DataCard
        title={t('Запись на секции закрыта')}
        note={t(
          'Ты не записан ни в одну секцию. Если хочешь заниматься, подойди к директору спорта — он может записать тебя сам',
        )}
      />
    )
  return <Choose data={data} onBack={mine ? () => setChanging(false) : undefined} />
}

function MySection({ data, onChange }: { data: MySectionData; onChange: () => void }) {
  const { leave } = useMySectionAction()
  const [leaving, setLeaving] = useState(false)
  const mine = data.enrollment!
  const slot = mine.slot!
  return (
    <div className="lay-main">
      <DataCard
        className="card--beam"
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
            <Button onClick={onChange}>{t('Сменить секцию или время')}</Button>
          </div>
        ) : (
          <p className="t-note">{t('Запись закрыта · сменить секцию можно через директора спорта')}</p>
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
                leave.mutate(undefined, {
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
function ChooseHour({ data }: { data: MySectionData }) {
  const { enroll } = useMySectionAction()
  const mine = data.enrollment!
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
  slot: SlotRow
  onPick: () => void
  busy: boolean
  action: string
}) {
  const free = slot.free ?? 0
  return (
    <div className="dir__row">
      <span className="dir__what">
        <b>{slotLong(slot)}</b>
        <span className="t-note">
          {[slot.room, t('свободно {n} из {total}', { n: free, total: slot.capacity })]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </span>
      {free === 0 ? (
        <Chip tone="neutral" size="sm">
          {t('мест нет')}
        </Chip>
      ) : (
        <span />
      )}
      <span className="dir__acts">
        {free > 0 && (
          <Button variant="outline" size="sm" disabled={busy} onClick={onPick}>
            {action}
          </Button>
        )}
      </span>
    </div>
  )
}

/** Запись открыта: секции со слотами своей параллели и свободными местами. */
function Choose({ data, onBack }: { data: MySectionData; onBack?: () => void }) {
  const { enroll } = useMySectionAction()
  const [confirm, setConfirm] = useState<{ section: string; slot: SlotRow } | null>(null)
  return (
    <>
      <DataCard
        title={t('Выбери секцию и время')}
        note={[
          data.enroll_until
            ? t('запись открыта до {when}', { when: formatDateTimeLong(data.enroll_until) })
            : '',
          t('Одна секция на ученика'),
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
        {data.sections.length === 0 && <EmptyNote what={tk('для твоей параллели занятий нет')} />}
      </DataCard>
      <div className="sport-choose">
        {data.sections.map((section) => (
          <DataCard key={section.id} title={section.title} note={section.address}>
            <div className="dir__rows">
              {section.slots.map((slot) => (
                <SlotLine
                  key={slot.id}
                  slot={slot}
                  busy={enroll.isPending}
                  onPick={() => setConfirm({ section: section.title, slot })}
                  action={data.enrollment?.slot?.id === slot.id ? t('выбрано') : t('Записаться')}
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
          <p className="t-note">
            {t('Ученик ходит в одну секцию. Пока запись открыта, можно отменить и выбрать другую')}
          </p>
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
