/**
 * «Мероприятия» — директор спорта (макет SEvents, 24.10.2026).
 *
 * Соревнования и мероприятия школы: ученик видит их в «Спорте» и подаёт
 * заявку участвовать или смотреть. Здесь — заявки выбранного мероприятия:
 * принять, отклонить, а принятому участнику — «Освободить от уроков» тем же
 * освобождением, что у олимпиад.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { downloadFile } from '../../api/client'
import {
  useDecideApplication,
  useReleasePlayer,
  useSaveSportEvent,
  useSportEventApplications,
  useSportEvents,
  type SportApplicationRow,
  type SportEventRow,
} from '../../api/directors'
import { useDirectoryEntries } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, ShowAll } from '../../components/patterns'
import {
  EmptyNote,
  Bar,
  Chip,
  DataCard,
  ErrorNote,
  Loading,
  ScreenHead,
  type Tone,
} from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDateTime, formatDateTimeLong, formatDayMonth } from '../../lib/format'
import { usePhone } from '../../phone'
import './directors.css'

export const STATUS_TONE: Record<string, Tone> = { pending: 'warn', accepted: 'good', declined: 'neutral' }

export function seatsWords(row: SportEventRow): string {
  return row.seats === null
    ? t('принято {n} · без ограничения мест', { n: row.accepted })
    : t('{n} из {total}', { n: row.accepted, total: row.seats })
}

export default function SportEvents() {
  const { data, isLoading, error } = useSportEvents()
  const [params, setParams] = useSearchParams()
  const [when, setWhen] = useState<'soon' | 'past'>('soon')
  const [creating, setCreating] = useState(params.get('new') === '1')
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const soon = data.rows.filter((row) => !row.past)
  const past = data.rows.filter((row) => row.past).reverse()
  const rows = when === 'soon' ? soon : past
  const picked = Number(params.get('open')) || rows[0]?.id || null

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Мероприятия')}
        subtitle={t('соревнования и мероприятия · ученики видят их в разделе «Спорт»')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить мероприятие')}</Button>}
      />
      <div className="filters">
        <Segmented
          value={when}
          onChange={setWhen}
          label={t('Когда')}
          items={[
            {
              value: 'soon',
              label: (
                <>
                  {t('Ближайшие')} <span className="tabs__n num">{soon.length}</span>
                </>
              ),
            },
            {
              value: 'past',
              label: (
                <>
                  {t('Прошедшие')} <span className="tabs__n num">{past.length}</span>
                </>
              ),
            },
          ]}
        />
      </div>
      <div className="lay-main lay-main--even">
        <DataCard
          title={when === 'soon' ? t('Ближайшие') : t('Прошедшие')}
          count={rows.length || undefined}
          empty={rows.length === 0 && t('мероприятий пока нет')}
        >
          <div className="dir__rows">
            <ShowAll limit={8}>
              {rows.map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{row.title}</b>
                    <span className="t-note">
                      {[formatDayMonth(row.starts_at), row.sport_title, row.place]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  {(row.pending ?? 0) > 0 ? (
                    <Chip tone="accent" size="sm">
                      {t('заявок {n}', { n: row.pending ?? 0 })}
                    </Chip>
                  ) : (
                    <Chip size="sm">{row.kind_title}</Chip>
                  )}
                  <span className="dir__acts">
                    <Button
                      variant={row.id === picked ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => setParams({ open: String(row.id) }, { replace: true })}
                    >
                      {t('Открыть')}
                    </Button>
                  </span>
                </div>
              ))}
            </ShowAll>
          </div>
        </DataCard>
        {picked !== null && <Applications id={picked} key={picked} />}
      </div>
      {creating && (
        <EventDialog
          onClose={() => setCreating(false)}
          onSaved={(row) => setParams({ open: String(row.id) }, { replace: true })}
        />
      )}
    </div>
  )
}

function Applications({ id }: { id: number }) {
  const phone = usePhone()
  const { data, isLoading, error } = useSportEventApplications(id)
  const decide = useDecideApplication()
  const [releasing, setReleasing] = useState<SportApplicationRow | null>(null)
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const event = data.event
  const set = (row: SportApplicationRow, status: 'accepted' | 'declined' | 'pending') =>
    decide.mutate(
      { id: row.id, status },
      {
        onSuccess: () =>
          toast.success(
            status === 'accepted'
              ? t('Заявка принята · ученик увидит статус')
              : status === 'declined'
                ? t('Заявка отклонена · ученик увидит статус')
                : t('Заявка снова ждёт решения'),
          ),
        onError: (reason) => toast.error(reason.message),
      },
    )
  // панель узкая: группа, заявка, время и статус — строками под именем, на виду одно действие
  const columns: Column<SportApplicationRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <>
          <b className="dir__name">{row.student?.short_name}</b>
          <span className="t-note dir__sub">
            {[row.student?.group, row.kind_title, formatDateTime(row.created_at)].filter(Boolean).join(' · ')}
          </span>
          {row.comment && <span className="t-note dir__sub">{row.comment}</span>}
          <span className="dir__sub">
            {row.release ? (
              <Chip tone="info" size="sm" className="dir__wrapchip">
                {t('освобождён · {span}', { span: row.release })}
              </Chip>
            ) : (
              <Chip tone={STATUS_TONE[row.status]} size="sm">
                {row.status_title}
              </Chip>
            )}
          </span>
        </>
      ),
    },
    {
      key: 'acts',
      title: '',
      width: '128px',
      actions: true,
      cell: (row) =>
        row.status === 'pending' ? (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={decide.isPending}
              onClick={() => set(row, 'accepted')}
            >
              {t('Принять')}
            </Button>
            <RowMenu>
              <RowMenuItem onClick={() => set(row, 'declined')}>{t('Отклонить')}</RowMenuItem>
            </RowMenu>
          </>
        ) : (
          row.kind === 'play' && (
            <RowMenu>
              {row.status === 'accepted' && !row.release && !event.past && (
                <RowMenuItem onClick={() => setReleasing(row)}>{t('Освободить от уроков')}</RowMenuItem>
              )}
              <RowMenuItem onClick={() => set(row, 'pending')}>{t('Вернуть')}</RowMenuItem>
            </RowMenu>
          )
        ),
    },
  ]
  const play = data.rows.filter((row) => row.kind === 'play')
  const watch = data.rows.filter((row) => row.kind === 'watch')
  return (
    <DataCard
      className="card--beam"
      title={event.title}
      note={[event.kind_title, event.sport_title].filter(Boolean).join(' · ')}
    >
      <div className="dir__headacts">
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            downloadFile(`/directors/sport-events/${event.id}/export/`, `${event.title}.xlsx`)
              .then(() => toast.success(t('Файл xlsx скачан')))
              .catch((reason: unknown) =>
                toast.error(reason instanceof Error ? reason.message : String(reason)),
              )
          }
        >
          {t('Скачать список')}
        </Button>
      </div>
      <div className="dir__lines">
        <div className="dir__line">
          <span>{t('Дата')}</span>
          <b>{formatDateTimeLong(event.starts_at)}</b>
        </div>
        <div className="dir__line">
          <span>{t('Место')}</span>
          <b>{event.place}</b>
        </div>
        <div className="dir__line">
          <span>{t('Участников принято')}</span>
          <b className="num">{seatsWords(event)}</b>
        </div>
        {event.spectators && (
          <div className="dir__line">
            <span>{t('Зрителей')}</span>
            <b className="num">{watch.length}</b>
          </div>
        )}
      </div>
      {event.seats !== null && <Bar percent={(event.accepted * 100) / Math.max(1, event.seats)} />}
      {data.rows.length === 0 ? (
        <EmptyNote what={tk('заявок пока нет')} who={tk('подают ученики в «Спорте»')} />
      ) : (
        <DataTable
          columns={columns}
          rows={[...play, ...watch]}
          rowKey={(row) => row.id}
          limit={8}
          fit={!phone}
        />
      )}
      {releasing && <ReleasePlayerDialog row={releasing} onClose={() => setReleasing(null)} />}
    </DataCard>
  )
}

function ReleasePlayerDialog({ row, onClose }: { row: SportApplicationRow; onClose: () => void }) {
  const release = useReleasePlayer()
  const [mode, setMode] = useState<'day' | 'slots'>('slots')
  const [from, setFrom] = useState('1')
  const [to, setTo] = useState('3')
  return (
    <Modal title={t('Освободить от уроков')} note={row.student?.full_name} onClose={onClose}>
      <Segmented
        value={mode}
        onChange={setMode}
        label={t('Уроки')}
        items={[
          { value: 'day', label: t('Весь день') },
          { value: 'slots', label: t('Выбрать уроки') },
        ]}
      />
      {mode === 'slots' && (
        <div className="dir__form">
          <Field
            kind="number"
            name="slot-from"
            label={t('С урока')}
            value={from}
            onChange={setFrom}
            min={1}
            max={10}
          />
          <Field
            kind="number"
            name="slot-to"
            label={t('По урок')}
            value={to}
            onChange={setTo}
            min={1}
            max={10}
          />
        </div>
      )}
      {release.error && <ErrorNote error={release.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={release.isPending}
          onClick={() =>
            release.mutate(
              {
                id: row.id,
                slot_from: mode === 'slots' ? Number(from) : null,
                slot_to: mode === 'slots' ? Number(to) : null,
              },
              { onSuccess: onClose },
            )
          }
        >
          {t('Освободить')}
        </Button>
      </div>
    </Modal>
  )
}

/** Новое мероприятие: название, тип, вид спорта, дата и время, место, места и зрители. */
export function EventDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved?: (row: SportEventRow) => void
}) {
  const save = useSaveSportEvent()
  const types = useDirectoryEntries('sport-types')
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<'competition' | 'event'>('competition')
  const [sport, setSport] = useState('')
  const [when, setWhen] = useState('')
  const [time, setTime] = useState('10:00')
  const [place, setPlace] = useState('')
  const [seats, setSeats] = useState('')
  const [spectators, setSpectators] = useState(true)
  return (
    <Modal title={t('Новое мероприятие')} note={t('ученики увидят в разделе «Спорт»')} onClose={onClose}>
      <div className="dir__form">
        <Field
          className="dir__wide"
          name="title"
          label={t('Название')}
          value={title}
          onChange={setTitle}
          autoFocus
        />
        <div className="dir__wide">
          <Segmented
            value={kind}
            onChange={setKind}
            label={t('Тип')}
            items={[
              { value: 'competition', label: t('Соревнование') },
              { value: 'event', label: t('Мероприятие') },
            ]}
          />
        </div>
        <Field
          kind="select"
          name="sport"
          label={t('Вид спорта')}
          value={sport}
          onChange={setSport}
          placeholder={t('Без вида спорта')}
          options={(types.data?.results ?? [])
            .filter((row) => row.is_active)
            .map((row) => ({ value: String(row.id), title: row.name }))}
        />
        <Field name="place" label={t('Место')} value={place} onChange={setPlace} />
        <Field kind="date" name="date" label={t('Дата')} value={when} onChange={setWhen} />
        <Field kind="time" name="time" label={t('Время')} value={time} onChange={setTime} />
        <Field
          kind="number"
          name="seats"
          label={t('Мест для участников')}
          value={seats}
          onChange={setSeats}
          min={1}
          hint={t('пусто — без ограничения')}
        />
        <Field
          kind="checkbox"
          name="spectators"
          label={t('Можно прийти зрителем')}
          checked={spectators}
          onChange={setSpectators}
        />
      </div>
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!title.trim() || !when || !place.trim() || save.isPending}
          onClick={() =>
            save.mutate(
              {
                title,
                kind,
                sport_type: sport ? Number(sport) : null,
                starts_at: `${when}T${time || '10:00'}:00`,
                place,
                seats: seats ? Number(seats) : null,
                spectators,
              },
              {
                onSuccess: (row) => {
                  toast.success(t('Ученики увидят в разделе «Спорт»'))
                  onSaved?.(row)
                  onClose()
                },
              },
            )
          }
        >
          {t('Опубликовать')}
        </Button>
      </div>
    </Modal>
  )
}
