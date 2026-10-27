/**
 * «Билеты» — директор спорта и администратор (макет STickets, 27.10.2026).
 *
 * Бесплатные билеты школы: анонс уходит ученикам сразу, кнопка «Забрать»
 * открывается в назначенную минуту у всех одновременно (по часам сервера),
 * один билет в руки. Слева раздачи «анонс / идёт / разобраны / прошло»,
 * справа карточка: старт, роздано, в очереди, сколько учеников получили анонс,
 * вкладки «Получили / Очередь / Отказались» со временем нажатия.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  useTicketActions,
  useTicketDrop,
  useTicketDrops,
  type DropStage,
  type TicketClaimRow,
} from '../../api/sport'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented } from '../../components/patterns'
import {
  Bar,
  Chip,
  DataCard,
  EmptyNote,
  ErrorNote,
  Loading,
  ScreenHead,
  type Tone,
} from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDateTimeLong, formatTime } from '../../lib/format'
import { usePhone } from '../../phone'
import '../directors/directors.css'
import './sport.css'

export const STAGE: Record<DropStage, { label: string; tone: Tone }> = {
  announce: { label: tk('анонс'), tone: 'info' },
  open: { label: tk('идёт'), tone: 'good' },
  gone: { label: tk('разобраны'), tone: 'warn' },
  past: { label: tk('прошло'), tone: 'neutral' },
}

const CLAIM_TONE: Record<string, Tone> = {
  received: 'good',
  queued: 'info',
  offered: 'accent',
  declined: 'neutral',
  left: 'neutral',
  expired: 'neutral',
  missed: 'bad',
}

/** «15:00:04.218» — время нажатия до миллисекунд: по нему идёт очередь. */
function pressedWords(value: string): string {
  const millis = value.match(/\.(\d{3})/)?.[1] ?? '000'
  const seconds = value.match(/T\d{2}:\d{2}:(\d{2})/)?.[1] ?? '00'
  return `${formatTime(value)}:${seconds}.${millis}`
}

export default function Tickets() {
  const { data, isLoading, error } = useTicketDrops()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const picked = Number(params.get('open')) || data.rows[0]?.id || null
  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Билеты')}
        subtitle={t('Бесплатные билеты от школы · кнопка «Забрать» открывается в назначенную минуту')}
        actions={<Button onClick={() => setCreating(true)}>{t('Новая раздача')}</Button>}
      />
      <div className="sport-pair">
        <DataCard
          title={t('Раздачи')}
          count={data.rows.length || undefined}
          empty={data.rows.length === 0 && t('раздач пока нет')}
        >
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
                  <Chip tone={STAGE[row.stage].tone} size="sm">
                    {t(STAGE[row.stage].label)}
                  </Chip>
                </span>
                <span className="t-note num">
                  {t('{n} билетов · старт {when}', { n: row.count, when: formatDateTimeLong(row.opens_at) })}
                </span>
              </Button>
            ))}
          </div>
        </DataCard>
        {picked !== null && <DropCard id={picked} key={picked} />}
      </div>
      {creating && (
        <DropDialog
          onClose={() => setCreating(false)}
          onSaved={(id) => setParams({ open: String(id) }, { replace: true })}
        />
      )}
    </div>
  )
}

function DropCard({ id }: { id: number }) {
  const phone = usePhone()
  const { data, isLoading, error } = useTicketDrop(id)
  const actions = useTicketActions()
  const [tab, setTab] = useState<'received' | 'queue' | 'declined'>('received')
  if (isLoading && !data) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const groups = {
    received: data.claims.filter((c) => c.status === 'received'),
    queue: data.claims.filter((c) => c.status === 'queued' || c.status === 'offered'),
    declined: data.claims.filter((c) => ['declined', 'left', 'expired', 'missed'].includes(c.status)),
  }
  const columns: Column<TicketClaimRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <>
          <b className="dir__name">{row.student.short_name}</b>
          <span className="t-note dir__sub">
            {[
              t('{n} параллель', { n: row.student.parallel }),
              row.student.group,
              pressedWords(row.pressed_at),
            ].join(' · ')}
          </span>
        </>
      ),
    },
    {
      key: 'status',
      title: t('Статус'),
      width: '140px',
      cell: (row) => (
        <Chip tone={CLAIM_TONE[row.status]} size="sm">
          {row.place
            ? t('в очереди №{n}', { n: row.place })
            : row.from_queue && row.status === 'received'
              ? t('из очереди')
              : row.status_title}
        </Chip>
      ),
    },
    {
      key: 'acts',
      title: '',
      width: '56px',
      actions: true,
      cell: (row) =>
        row.status === 'received' && data.stage !== 'past' ? (
          <RowMenu>
            <RowMenuItem
              onClick={() =>
                actions.missed.mutate(row.id, {
                  onSuccess: () => toast.success(t('Билет уходит первому в очереди')),
                  onError: (reason) => toast.error(reason.message),
                })
              }
            >
              {t('Не забрал')}
            </RowMenuItem>
          </RowMenu>
        ) : null,
    },
  ]
  const shown = groups[tab]
  return (
    <DataCard
      className="card--beam"
      title={data.title}
      note={[formatDateTimeLong(data.event_at), data.place].join(' · ')}
      right={
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            downloadFile(`/sport/tickets/${data.id}/export/`, `${data.title}.xlsx`)
              .then(() => toast.success(t('Файл xlsx скачан · список на вход')))
              .catch((reason: unknown) =>
                toast.error(reason instanceof Error ? reason.message : String(reason)),
              )
          }
        >
          {t('Скачать список')}
        </Button>
      }
    >
      <div className="dir__lines">
        <div className="dir__line">
          <span>{t('Старт раздачи')}</span>
          <b>{formatDateTimeLong(data.opens_at)}</b>
        </div>
        <div className="dir__line">
          <span>{t('Роздано')}</span>
          <b className="num">{t('{n} из {total}', { n: data.received, total: data.count })}</b>
        </div>
        <div className="dir__line">
          <span>{t('В очереди')}</span>
          <b className="num">{data.queued ?? 0}</b>
        </div>
        <div className="dir__line">
          <span>{t('Анонс получили')}</span>
          <b className="num">{data.announced}</b>
        </div>
        <div className="dir__line">
          <span>{t('Где забрать')}</span>
          <b>{data.pickup}</b>
        </div>
      </div>
      <Bar percent={(data.received * 100) / Math.max(1, data.count)} />
      {data.stage === 'announce' ? (
        <EmptyNote
          what={tk('Раздача ещё не началась')}
          who={tk('кнопка «Забрать» откроется у всех в одну секунду')}
        />
      ) : (
        <>
          <Segmented
            value={tab}
            onChange={setTab}
            label={t('Список')}
            items={[
              { value: 'received', label: t('Получили {n}', { n: groups.received.length }) },
              { value: 'queue', label: t('Очередь {n}', { n: groups.queue.length }) },
              { value: 'declined', label: t('Отказались {n}', { n: groups.declined.length }) },
            ]}
          />
          {shown.length === 0 ? (
            <EmptyNote what={tk('здесь пока никого')} />
          ) : (
            <DataTable columns={columns} rows={shown} rowKey={(row) => row.id} limit={8} fit={!phone} />
          )}
        </>
      )}
    </DataCard>
  )
}

const AUDIENCE = [
  { value: '8-11', title: tk('Все параллели 8–11') },
  { value: '8-9', title: tk('параллели 8–9') },
  { value: '10-11', title: tk('параллели 10–11') },
]

function DropDialog({ onClose, onSaved }: { onClose: () => void; onSaved: (id: number) => void }) {
  const { publish } = useTicketActions()
  const [title, setTitle] = useState('')
  const [eventDate, setEventDate] = useState('')
  const [eventTime, setEventTime] = useState('19:00')
  const [place, setPlace] = useState('')
  const [count, setCount] = useState('20')
  const [openDate, setOpenDate] = useState('')
  const [openTime, setOpenTime] = useState('15:00')
  const [pickup, setPickup] = useState('')
  const [audience, setAudience] = useState('8-11')
  const [from, to] = audience.split('-').map(Number)
  return (
    <Modal
      title={t('Новая раздача билетов')}
      note={t('Один билет в руки · за 5 минут до старта всем напоминание · на ответ из очереди 30 минут')}
      onClose={onClose}
      wide
    >
      <div className="dir__form">
        <Field
          className="dir__wide"
          name="title"
          label={t('Событие')}
          value={title}
          onChange={setTitle}
          autoFocus
        />
        <Field
          kind="date"
          name="event-date"
          label={t('Когда событие')}
          value={eventDate}
          onChange={setEventDate}
        />
        <Field
          kind="time"
          name="event-time"
          label={t('Время события')}
          value={eventTime}
          onChange={setEventTime}
        />
        <Field name="place" label={t('Где')} value={place} onChange={setPlace} />
        <Field
          kind="number"
          name="count"
          label={t('Сколько билетов')}
          value={count}
          onChange={setCount}
          min={1}
        />
        <Field
          kind="date"
          name="open-date"
          label={t('Старт раздачи')}
          value={openDate}
          onChange={setOpenDate}
        />
        <Field
          kind="time"
          name="open-time"
          label={t('Время старта')}
          value={openTime}
          onChange={setOpenTime}
        />
        <Field
          className="dir__wide"
          name="pickup"
          label={t('Где и до когда забрать билет')}
          value={pickup}
          onChange={setPickup}
          placeholder={t('Кабинет директора спорта, до 18:00 накануне')}
        />
        <Field
          className="dir__wide"
          kind="select"
          name="audience"
          label={t('Кому')}
          value={audience}
          onChange={setAudience}
          options={AUDIENCE.map((row) => ({ value: row.value, title: t(row.title) }))}
        />
      </div>
      {publish.error && <ErrorNote error={publish.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={
            !title.trim() ||
            !eventDate ||
            !openDate ||
            !place.trim() ||
            !pickup.trim() ||
            !Number(count) ||
            publish.isPending
          }
          onClick={() =>
            publish.mutate(
              {
                title,
                event_at: `${eventDate}T${eventTime || '19:00'}:00`,
                place,
                count: Number(count),
                opens_at: `${openDate}T${openTime || '15:00'}:00`,
                pickup,
                parallel_from: from,
                parallel_to: to,
              },
              {
                onSuccess: (row) => {
                  toast.success(
                    t('Анонс отправлен ученикам · кнопка откроется в {time}', {
                      time: formatTime(row.opens_at),
                    }),
                  )
                  onSaved(row.id)
                  onClose()
                },
              },
            )
          }
        >
          {t('Опубликовать анонс')}
        </Button>
      </div>
    </Modal>
  )
}
